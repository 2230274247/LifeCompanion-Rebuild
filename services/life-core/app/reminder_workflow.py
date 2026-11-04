from __future__ import annotations

import threading
from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ReminderState(TypedDict, total=False):
    owner_id: str
    object_id: str
    workflow_version: int
    status: str
    revision: int
    missing_fields: list[str]
    reminder_id: str | None
    command: dict | None


class ReminderWorkflow:
    """Durable business nodes; the bound authority always reads SQLite first."""

    def __init__(self, database_path: Path, authority, *, task=False):
        self.database_path, self.authority = database_path, authority
        self.prefix = "reminder-task" if task else "reminder"
        self.lock = threading.RLock()
        graph = StateGraph(ReminderState)
        graph.add_node("load_authority", self._load)
        for name in ("collect_missing", "await_confirmation", "active", "unknown"):
            graph.add_node(name, self._wait)
            graph.add_conditional_edges(name, self._dispatch, {
                "patch": "apply_patch", "select": "apply_patch",
                "confirm": "authorize", "update": "authorize",
                "cancel": "cancel", "reconcile": "reconcile",
            })
        graph.add_node("apply_patch", self._patch)
        graph.add_conditional_edges(
            "apply_patch",
            lambda state: "authorize" if state["command"]["action"] == "confirm" else "load_authority",
            {"authorize": "authorize", "load_authority": "load_authority"})
        graph.add_node("authorize", self._authorize)
        graph.add_conditional_edges(
            "authorize", lambda state: "update" if state["command"]["action"] == "update" else "commit",
            {"update": "update", "commit": "commit"})
        for name in ("commit", "update", "cancel", "reconcile"):
            graph.add_node(name, self._operation(name))
            graph.add_edge(name, "load_authority")
        graph.add_edge(START, "load_authority")
        graph.add_conditional_edges("load_authority", self._phase, {
            "collect_missing": "collect_missing", "await_confirmation": "await_confirmation",
            "active": "active", "unknown": "unknown", "end": END,
        })
        self.graph_builder = graph

    def _load(self, state):
        return {**self.authority._workflow_load(state["owner_id"], state["object_id"]),
                "command": None}

    @staticmethod
    def _phase(state):
        if state["status"] in ("cancelled", "expired"):
            return "end"
        if state["status"] in ("scheduled", "due", "completed"):
            return "active"
        if state["status"] in ("unknown", "creating"):
            return "unknown"
        return "collect_missing" if state["missing_fields"] else "await_confirmation"

    @staticmethod
    def _wait(state):
        command = interrupt({
            "object_id": state["object_id"], "status": state["status"],
            "revision": state["revision"], "missing_fields": state["missing_fields"],
        })
        return {"command": command}

    @staticmethod
    def _dispatch(state):
        action = state["command"].get("action")
        if action not in {"patch", "select", "confirm", "update", "cancel", "reconcile"}:
            raise ValueError("UNSUPPORTED_REMINDER_OPERATION")
        return action

    def _patch(self, state):
        command = state["command"]
        value = self.authority._workflow_patch(
            state["owner_id"], state["object_id"], command)
        if command["action"] == "select" and not value["missing_fields"] and not value["error_code"]:
            return {"command": {
                "action": "confirm", "revision": value["revision"],
                "idempotency_key": f"{state['object_id']}:{value['revision']}",
            }}
        return {}

    def _authorize(self, state):
        self.authority._workflow_authorize(
            state["owner_id"], state["object_id"], state["command"])
        return {}

    def _operation(self, name):
        def execute(state):
            getattr(self.authority, f"_workflow_{name}")(
                state["owner_id"], state["object_id"], state["command"])
            return {}
        return execute

    def _config(self, owner, object_id):
        return {"configurable": {"thread_id": f"{self.prefix}:{owner}:{object_id}"}}

    @staticmethod
    def _interrupted(snapshot):
        return any(task.interrupts for task in snapshot.tasks)

    def _prepare(self, graph, config, owner, object_id):
        snapshot = graph.get_state(config)
        if snapshot.values.get("workflow_version") != 2 or not self._interrupted(snapshot):
            # Legacy audit-only checkpoints and failed nodes restart from business
            # authority. No old input may replay a remote write without a new command.
            graph.invoke({"owner_id": owner, "object_id": object_id,
                          "workflow_version": 2, "command": None}, config=config)

    def open(self, owner, object_id):
        self.authority._workflow_load(owner, object_id)
        with self.lock, SqliteSaver.from_conn_string(str(self.database_path)) as saver:
            graph = self.graph_builder.compile(checkpointer=saver)
            self._prepare(graph, self._config(owner, object_id), owner, object_id)

    def send(self, owner, object_id, command):
        self.authority._workflow_load(owner, object_id)
        with self.lock, SqliteSaver.from_conn_string(str(self.database_path)) as saver:
            graph = self.graph_builder.compile(checkpointer=saver)
            config = self._config(owner, object_id)
            self._prepare(graph, config, owner, object_id)
            if self._interrupted(graph.get_state(config)):
                graph.invoke(Command(resume=command), config=config)
            elif command["action"] not in {"cancel", "reconcile", "confirm"}:
                raise HTTPException(409, detail={"code": "DRAFT_LOCKED"})

    def snapshot(self, owner, object_id):
        with self.lock, SqliteSaver.from_conn_string(str(self.database_path)) as saver:
            graph = self.graph_builder.compile(checkpointer=saver)
            snapshot = graph.get_state(self._config(owner, object_id))
            return {"next": list(snapshot.next), "interrupted": self._interrupted(snapshot),
                    "values": dict(snapshot.values)}
