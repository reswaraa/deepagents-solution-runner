"""Runtime that drives a built DeepAgent through a single user request.

The runner is responsible for:

* applying input guardrails before invoking the model
* invoking the agent with a stable ``thread_id`` (so HITL can resume)
* converting the interrupt payload from ``HumanInTheLoopMiddleware`` into
  user-facing approval requests, gathering decisions, and resuming
* logging every meaningful event to JSONL
* applying output guardrails and surfacing the final answer

The runner does **not** call any real LLM unless the resolved model has
credentials; on the no-key path it logs the planned events and returns
a stub answer so config/observability/eval flows can still be exercised.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.adapters.observability_adapter import RunContext, RunLogger
from app.deepagent_builder import BuiltAgent, RuntimeContext

# ---------------------------------------------------------------------------
# Approval data types
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequest:
    """One pending approval — corresponds to one tool call the agent wants."""

    tool_name: str
    args: dict[str, Any]
    description: str | None
    allowed_decisions: list[str]


@dataclass
class ApprovalDecision:
    """A reviewer's response to an approval request."""

    decision: str  # 'approve' | 'edit' | 'reject'
    edited_args: dict[str, Any] | None = None
    message: str | None = None

    def as_hitl_payload(self, request: ApprovalRequest) -> dict[str, Any]:
        if self.decision == "approve":
            return {"type": "approve"}
        if self.decision == "edit":
            return {
                "type": "edit",
                "edited_action": {
                    "name": request.tool_name,
                    "args": dict(self.edited_args or request.args),
                },
            }
        if self.decision == "reject":
            payload: dict[str, Any] = {"type": "reject"}
            if self.message:
                payload["message"] = self.message
            return payload
        raise ValueError(f"unknown decision type: {self.decision}")


ApprovalCallback = Callable[[list[ApprovalRequest]], list[ApprovalDecision]]


def auto_reject_callback(requests: list[ApprovalRequest]) -> list[ApprovalDecision]:
    """Default callback: always reject — safe for tests / non-interactive use."""

    return [ApprovalDecision(decision="reject", message="auto-rejected") for _ in requests]


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    thread_id: str
    request_id: str
    final_answer: str
    triggered_guardrails: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str | None = None
    executed_tools: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SolutionRunner:
    """Single-shot runner: validates, invokes, handles HITL, logs, returns."""

    def __init__(self, built: BuiltAgent) -> None:
        self.built = built

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        request_id: str | None = None,
        user_id: str = "anonymous",
        department: str = "unknown",
        on_approval: ApprovalCallback = auto_reject_callback,
        max_approval_rounds: int = 8,
    ) -> RunResult:
        cfg = self.built.solution.config
        thread_id = thread_id or f"thread-{uuid.uuid4().hex[:8]}"
        request_id = request_id or f"REQ-{uuid.uuid4().hex[:6].upper()}"

        run_ctx = RunContext(
            solution_id=cfg.solution_id,
            thread_id=thread_id,
            request_id=request_id,
        )
        logger = self.built.observability_adapter.run_logger(run_ctx)
        logger.log("run_started", message_preview=message[:200])
        logger.log(
            "model_selected",
            logical_name=self.built.resolved_model.logical_name,
            provider_model=self.built.resolved_model.provider_model,
            has_credentials=self.built.resolved_model.has_credentials,
        )
        logger.log("user_message_received", message=message)

        # ------------------------------------------------------------------
        # Input guardrails
        # ------------------------------------------------------------------

        triggered: list[str] = []
        input_results = self.built.guardrail_adapter.check_input(message)
        for gr in input_results:
            if gr.triggered:
                triggered.append(gr.name)
                logger.log(
                    "guardrail_triggered",
                    stage="input",
                    name=gr.name,
                    detail=gr.detail,
                )

        # block_prompt_injection blocks the run
        if any(gr.name == "block_prompt_injection" and gr.triggered for gr in input_results):
            answer = (
                "I cannot process this request because it contains a prompt-"
                "injection pattern that violates the policy. Please rephrase "
                "the instruction without overriding safety guidance."
            )
            logger.log("final_response", answer_preview=answer[:200], blocked=True)
            logger.log("run_completed", blocked=True)
            return RunResult(
                thread_id=thread_id,
                request_id=request_id,
                final_answer=answer,
                triggered_guardrails=triggered,
                events=self._read_run_events(thread_id),
                blocked=True,
                blocked_reason="block_prompt_injection",
            )

        # ------------------------------------------------------------------
        # No-key short circuit (config/observability still exercised)
        # ------------------------------------------------------------------

        if not self.built.resolved_model.has_credentials:
            answer = (
                "[stub-run] No LLM credentials available. The solution config, "
                "tool registry, governance, and observability layers were "
                "exercised, but no model was invoked. Set ANTHROPIC_API_KEY (or "
                "the relevant provider key) and re-run for a full demo."
            )
            logger.log("final_response", answer_preview=answer[:200], stubbed=True)
            logger.log("run_completed", stubbed=True)
            return RunResult(
                thread_id=thread_id,
                request_id=request_id,
                final_answer=answer,
                triggered_guardrails=triggered,
                events=self._read_run_events(thread_id),
            )

        # ------------------------------------------------------------------
        # Live agent invocation + interrupt loop
        # ------------------------------------------------------------------

        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        runtime_ctx = RuntimeContext(
            user_id=user_id,
            department=department,
            solution_id=cfg.solution_id,
            request_id=request_id,
        )
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = self.built.agent.invoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                context=runtime_ctx,
            )
        except Exception as exc:
            logger.log("run_failed", error=str(exc))
            raise

        executed_tools: list[str] = []
        rounds = 0
        while True:
            interrupts = state.get("__interrupt__") or []
            if not interrupts:
                break
            rounds += 1
            if rounds > max_approval_rounds:
                logger.log(
                    "run_failed", error="max approval rounds exceeded"
                )
                raise RuntimeError("Exceeded max approval rounds.")

            requests = _extract_approval_requests(interrupts)
            for req in requests:
                logger.log(
                    "approval_requested",
                    tool_name=req.tool_name,
                    tool_args=req.args,
                    allowed_decisions=req.allowed_decisions,
                    description=req.description,
                )

            decisions = on_approval(requests)
            if len(decisions) != len(requests):
                raise ValueError(
                    f"approval callback returned {len(decisions)} decisions "
                    f"for {len(requests)} requests"
                )

            hitl_payload = []
            for req, dec in zip(requests, decisions):
                logger.log(
                    "approval_decision",
                    tool_name=req.tool_name,
                    decision=dec.decision,
                    edited_args=dec.edited_args,
                )
                hitl_payload.append(dec.as_hitl_payload(req))

            state = self.built.agent.invoke(
                Command(resume={"decisions": hitl_payload}),
                config=config,
                context=runtime_ctx,
            )

        # Pull executed tool names from the message log.
        executed_tools = _extract_executed_tool_names(state)
        for tn in executed_tools:
            logger.log("action_executed", tool_name=tn)

        final_answer = _extract_final_answer(state)

        # Output guardrails
        out_results = self.built.guardrail_adapter.check_output(
            final_answer, context={"executed_tools": set(executed_tools)}
        )
        for gr in out_results:
            if gr.triggered:
                triggered.append(gr.name)
                logger.log(
                    "guardrail_triggered",
                    stage="output",
                    name=gr.name,
                    detail=gr.detail,
                )

        logger.log("final_response", answer_preview=final_answer[:300])
        logger.log("run_completed")

        return RunResult(
            thread_id=thread_id,
            request_id=request_id,
            final_answer=final_answer,
            triggered_guardrails=triggered,
            events=self._read_run_events(thread_id),
            executed_tools=executed_tools,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_run_events(self, thread_id: str) -> list[dict[str, Any]]:
        return [
            e
            for e in self.built.observability_adapter.read_events()
            if e.get("thread_id") == thread_id
        ]


# ---------------------------------------------------------------------------
# Interrupt parsing
# ---------------------------------------------------------------------------


def _extract_approval_requests(interrupts: Any) -> list[ApprovalRequest]:
    """Pull HITLRequest data out of the LangGraph interrupt payload."""

    out: list[ApprovalRequest] = []
    for itr in interrupts:
        value = getattr(itr, "value", None)
        if value is None and isinstance(itr, dict):
            value = itr.get("value")
        if value is None:
            continue
        action_requests = value.get("action_requests", []) if isinstance(value, dict) else []
        review_configs = value.get("review_configs", []) if isinstance(value, dict) else []
        review_lookup = {
            rc.get("action_name"): rc.get("allowed_decisions", [])
            for rc in review_configs
            if isinstance(rc, dict)
        }
        for action in action_requests:
            if not isinstance(action, dict):
                continue
            name = action.get("name", "")
            args = action.get("args", {}) or {}
            out.append(
                ApprovalRequest(
                    tool_name=name,
                    args=args,
                    description=action.get("description"),
                    allowed_decisions=list(review_lookup.get(name, [])),
                )
            )
    return out


def _extract_executed_tool_names(state: Any) -> list[str]:
    """Return tool names that produced ToolMessages in the run."""

    from langchain_core.messages import ToolMessage

    names: list[str] = []
    msgs = state.get("messages", []) if isinstance(state, dict) else []
    for m in msgs:
        if isinstance(m, ToolMessage) and m.status == "success":
            names.append(m.name or "")
    return [n for n in names if n]


def _extract_final_answer(state: Any) -> str:
    """Return the text content of the last AIMessage in the state."""

    from langchain_core.messages import AIMessage

    msgs = state.get("messages", []) if isinstance(state, dict) else []
    for m in reversed(msgs):
        if isinstance(m, AIMessage):
            content = m.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                return "\n".join(parts)
    return ""
