from __future__ import annotations

import threading

from langchain_core.callbacks import BaseCallbackHandler

import json

from .store import utc_now


class MemoryModelBudgetError(ValueError):
    code = "MEMORY_MODEL_REQUEST_BUDGET"


class MemoryModelAudit(BaseCallbackHandler):
    raise_error = True

    def __init__(self, store, user_id, model, *, request_budget=0, source_message_id=None):
        self.store, self.user_id, self.model = store, user_id, model
        self.request_budget = request_budget
        self.source_message_id = source_message_id
        self.calls = 0
        self.lock = threading.Lock()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        with self.lock:
            if self.calls >= 3:
                raise MemoryModelBudgetError("MEMORY_MODEL_CALL_LIMIT")
            self.calls += 1
        with self.store.connect() as db:
            # Reserve before sending; failures and earlier processes also consume the budget.
            db.execute("BEGIN IMMEDIATE")
            if self.request_budget and db.execute(
                "SELECT count(*) FROM memory_model_calls"
            ).fetchone()[0] >= self.request_budget:
                raise MemoryModelBudgetError("MEMORY_MODEL_REQUEST_BUDGET")
            db.execute(
                "INSERT INTO memory_model_calls"
                "(call_id,user_id,model,status,started_at,source_message_id) "
                "VALUES (?,?,?,'running',?,?)",
                (str(run_id),self.user_id,self.model,utc_now(),self.source_message_id),
            )

    def on_llm_end(self, response, *, run_id, **kwargs):
        usage = (response.llm_output or {}).get("token_usage") or {}
        outputs = []
        for generation in response.generations:
            for item in generation:
                content = getattr(item, "text", None)
                message = getattr(item, "message", None)
                if content is None:
                    content = getattr(message, "content", None)
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    outputs.append(json.dumps(
                        {"content": content, "tool_calls": tool_calls},
                        ensure_ascii=False,
                        default=lambda value: (
                            value.model_dump()
                            if hasattr(value, "model_dump")
                            else str(value)
                        ),
                    ))
                elif content is not None and (
                    not isinstance(content, str) or content.strip()
                ):
                    outputs.append(
                        content if isinstance(content, str)
                        else json.dumps(content, ensure_ascii=False, default=str)
                    )
                metadata = getattr(message, "usage_metadata", None)
                if metadata:
                    usage = {"prompt_tokens":metadata.get("input_tokens"),
                             "completion_tokens":metadata.get("output_tokens")}
                    break
        with self.store.connect() as db:
            db.execute(
                "UPDATE memory_model_calls SET status='succeeded',completed_at=?,"
                "input_tokens=?,output_tokens=?,raw_output=? WHERE call_id=?",
                (
                    utc_now(),
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    "\n".join(outputs) or None,
                    str(run_id),
                ),
            )

    def on_llm_error(self, error, *, run_id, **kwargs):
        code = f"{type(error).__name__}:{getattr(error, 'status_code', 'no_status')}"
        with self.store.connect() as db:
            db.execute(
                "UPDATE memory_model_calls SET status='failed',completed_at=?,"
                "error_code=? WHERE call_id=?",
                (utc_now(),code,str(run_id)),
            )
