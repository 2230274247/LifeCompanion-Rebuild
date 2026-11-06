from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class ReminderTransition(TypedDict):
    owner_id: str
    draft_id: str
    action: Literal["proposed", "collect_missing", "ready", "committing",
                    "active", "cancelled", "unknown"]
    revision: int
    missing_fields: list[str]
    reminder_id: str | None


class ReminderWorkflow:
    """Persistent workflow checkpoints supplement the SQLite reminder authority."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.lock = threading.RLock()
        graph = StateGraph(ReminderTransition)
        graph.add_node("record_transition", lambda state: {})
        graph.add_edge(START, "record_transition")
        graph.add_edge("record_transition", END)
        self.graph_builder = graph

    def transition(self, state: ReminderTransition) -> dict:
        with self.lock:
            thread_id = f"reminder:{state['owner_id']}:{state['draft_id']}"
            with SqliteSaver.from_conn_string(str(self.database_path)) as checkpointer:
                graph = self.graph_builder.compile(checkpointer=checkpointer)
                config = {"configurable": {"thread_id": thread_id}}
                result = graph.invoke(state, config=config)
                snapshot = graph.get_state(config)
                return {
                    "checkpoint_id": snapshot.config["configurable"]["checkpoint_id"],
                    "status": result["action"],
                    "revision": result["revision"],
                }
