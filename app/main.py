"""Command-line entry point for the DeepAgents Solution Runner.

Usage examples (see README for the full set):

    python -m app.main validate-config --solution solutions/.../solution.yaml
    python -m app.main list-tools     --solution solutions/.../solution.yaml
    python -m app.main run            --solution solutions/.../solution.yaml --message "..."
    python -m app.main eval           --solution solutions/.../solution.yaml
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.adapters.evaluation_adapter import MockEvaluationAdapter
from app.config_loader import ConfigError, load_solution
from app.deepagent_builder import DeepAgentSolutionBuilder
from app.runner import ApprovalDecision, ApprovalRequest, SolutionRunner

app = typer.Typer(
    add_completion=False,
    help="Config-first runtime for DeepAgents-based internal AI solutions.",
)
console = Console()


# ---------------------------------------------------------------------------
# validate-config
# ---------------------------------------------------------------------------


@app.command("validate-config")
def validate_config(
    solution: Path = typer.Option(..., "--solution", help="Path to solution.yaml"),
) -> None:
    """Validate the schema and referenced files; print a one-line summary."""

    try:
        loaded = load_solution(solution)
    except ConfigError as exc:
        console.print(f"[red]Invalid config:[/red] {exc}")
        raise typer.Exit(code=1)
    cfg = loaded.config
    console.print(
        Panel.fit(
            f"[green]OK[/green]: {cfg.solution_id}\n"
            f"runtime: {cfg.runtime}  env: {cfg.environment}\n"
            f"tools: {len(cfg.tools)}  subagents: {len(cfg.subagents)}  "
            f"skills: {len(cfg.skills)}\n"
            f"model: {cfg.model.logical_name} → {cfg.model.provider_model}",
            title="Config validated",
        )
    )


# ---------------------------------------------------------------------------
# list-tools
# ---------------------------------------------------------------------------


@app.command("list-tools")
def list_tools(
    solution: Path = typer.Option(..., "--solution", help="Path to solution.yaml"),
) -> None:
    """List the configured tools, their risk class, and approval policy."""

    loaded = _safe_load(solution)
    table = Table(title=f"Tools for {loaded.config.solution_id}")
    table.add_column("Name")
    table.add_column("Adapter")
    table.add_column("Risk")
    table.add_column("Approval", justify="center")
    table.add_column("Decisions")
    for t in loaded.config.tools:
        table.add_row(
            t.name,
            t.adapter,
            t.risk.value,
            "[red]yes[/red]" if t.approval_required else "[green]no[/green]",
            ", ".join(d.value for d in t.allowed_decisions or []) or "-",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command("run")
def run_command(
    solution: Path = typer.Option(..., "--solution", help="Path to solution.yaml"),
    message: str = typer.Option(..., "--message", help="User instruction."),
    thread_id: Optional[str] = typer.Option(None, "--thread-id"),
    request_id: Optional[str] = typer.Option(None, "--request-id"),
    user_id: str = typer.Option("anonymous", "--user-id"),
    department: str = typer.Option("unknown", "--department"),
    yes: bool = typer.Option(
        False, "--yes", help="Auto-approve every interrupt (no prompt)."
    ),
    no: bool = typer.Option(
        False, "--no", help="Auto-reject every interrupt (no prompt)."
    ),
) -> None:
    """Invoke the agent with one user message. Interactive HITL by default."""

    loaded = _safe_load(solution)
    built = DeepAgentSolutionBuilder().build(loaded)
    runner = SolutionRunner(built)

    callback = _interactive_callback
    if yes:
        callback = _auto_approve_callback
    elif no:
        callback = _auto_reject_callback

    result = runner.run(
        message,
        thread_id=thread_id,
        request_id=request_id,
        user_id=user_id,
        department=department,
        on_approval=callback,
    )

    console.print(
        Panel.fit(
            result.final_answer or "[i]no answer[/i]",
            title=f"Final answer (thread={result.thread_id})",
        )
    )
    if result.triggered_guardrails:
        console.print(
            f"[yellow]Guardrails triggered:[/yellow] {result.triggered_guardrails}"
        )
    if result.executed_tools:
        console.print(f"[cyan]Tools executed:[/cyan] {result.executed_tools}")
    if result.blocked:
        console.print(f"[red]Run blocked:[/red] {result.blocked_reason}")
    console.print(
        f"[dim]Events written to {built.observability_adapter.output_path}[/dim]"
    )


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------


@app.command("eval")
def eval_command(
    solution: Path = typer.Option(..., "--solution", help="Path to solution.yaml"),
    dataset: Optional[Path] = typer.Option(
        None, "--dataset", help="Override eval dataset path (JSONL)."
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Auto-approve interrupts when running live."
    ),
) -> None:
    """Run deterministic evaluation cases against the solution."""

    loaded = _safe_load(solution)
    if dataset is not None:
        # Allow override for ad-hoc datasets
        cases_text = dataset.read_text(encoding="utf-8").splitlines()
        cases = [
            _eval_case_from_dict(json.loads(line))
            for line in cases_text
            if line.strip()
        ]
    else:
        cases = MockEvaluationAdapter.load_cases(loaded)

    built = DeepAgentSolutionBuilder().build(loaded)

    # Truncate the JSONL log before the eval run so the report is clean.
    built.observability_adapter.truncate()

    runner = SolutionRunner(built)
    table = Table(title=f"Eval report — {loaded.config.solution_id}")
    table.add_column("Case")
    table.add_column("Status")
    table.add_column("Details")

    passed = failed = stubbed = 0
    for case in cases:
        decisions = case.approval_decisions
        callback = _make_scripted_callback(decisions)
        result = runner.run(
            case.input,
            thread_id=f"eval-{case.id}",
            request_id=f"EVAL-{case.id}",
            on_approval=callback,
        )
        # Run mode: if we stubbed the model, count separately
        stubbed_run = result.final_answer.startswith("[stub-run]")
        if stubbed_run:
            stubbed += 1
            table.add_row(case.id, "[dim]stubbed[/dim]", "no LLM key")
            continue
        case_result = MockEvaluationAdapter.evaluate_case(
            case,
            result.events,
            result.final_answer,
            triggered_guardrails=result.triggered_guardrails,
        )
        if case_result.passed:
            passed += 1
            table.add_row(case.id, "[green]PASS[/green]", "")
        else:
            failed += 1
            table.add_row(case.id, "[red]FAIL[/red]", case_result.failure_summary())

    console.print(table)
    console.print(
        f"Total: {len(cases)}  [green]passed: {passed}[/green]  "
        f"[red]failed: {failed}[/red]  [dim]stubbed: {stubbed}[/dim]"
    )
    if failed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_load(solution: Path):
    try:
        return load_solution(solution)
    except ConfigError as exc:
        console.print(f"[red]Invalid config:[/red] {exc}")
        raise typer.Exit(code=1)


def _eval_case_from_dict(d: dict) -> "MockEvaluationAdapter.load_cases.__wrapped__":
    from app.adapters.evaluation_adapter import EvalCase

    return EvalCase(
        id=d["id"],
        input=d["input"],
        approval_decisions=d.get("approval_decisions", []),
        expected=d.get("expected", {}),
    )


def _interactive_callback(requests: list[ApprovalRequest]) -> list[ApprovalDecision]:
    decisions: list[ApprovalDecision] = []
    for req in requests:
        console.print(
            Panel.fit(
                f"[bold]Tool:[/bold] {req.tool_name}\n"
                f"[bold]Args:[/bold] {json.dumps(req.args, indent=2)}\n"
                f"[bold]Allowed decisions:[/bold] {', '.join(req.allowed_decisions)}",
                title="Approval required",
            )
        )
        choice = typer.prompt(
            "Decision (approve / edit / reject)", default="approve"
        ).strip().lower()
        if choice == "edit":
            raw = typer.prompt(
                "New args as JSON",
                default=json.dumps(req.args),
            )
            try:
                edited = json.loads(raw)
            except json.JSONDecodeError:
                console.print("[red]Invalid JSON — treating as reject.[/red]")
                decisions.append(
                    ApprovalDecision(decision="reject", message="invalid edit JSON")
                )
                continue
            decisions.append(
                ApprovalDecision(decision="edit", edited_args=edited)
            )
        elif choice == "reject":
            msg = typer.prompt("Optional message", default="")
            decisions.append(
                ApprovalDecision(decision="reject", message=msg or None)
            )
        else:
            decisions.append(ApprovalDecision(decision="approve"))
    return decisions


def _auto_approve_callback(
    requests: list[ApprovalRequest],
) -> list[ApprovalDecision]:
    return [ApprovalDecision(decision="approve") for _ in requests]


def _auto_reject_callback(
    requests: list[ApprovalRequest],
) -> list[ApprovalDecision]:
    return [
        ApprovalDecision(decision="reject", message="auto-rejected via --no")
        for _ in requests
    ]


def _make_scripted_callback(script: list[dict]):
    """Build an approval callback driven by an eval case's scripted decisions."""

    # script: list of {"tool": str, "decision": str, "edited_args": dict?}
    # We replay decisions in order; if no scripted entry exists for a tool
    # the callback rejects (safe default).
    queue = list(script)

    def _callback(requests: list[ApprovalRequest]) -> list[ApprovalDecision]:
        decisions: list[ApprovalDecision] = []
        for req in requests:
            match = next(
                (i for i, s in enumerate(queue) if s.get("tool") == req.tool_name),
                None,
            )
            if match is None:
                decisions.append(
                    ApprovalDecision(decision="reject", message="no scripted decision")
                )
                continue
            entry = queue.pop(match)
            dec = entry.get("decision", "reject")
            decisions.append(
                ApprovalDecision(
                    decision=dec,
                    edited_args=entry.get("edited_args"),
                    message=entry.get("message"),
                )
            )
        return decisions

    return _callback


if __name__ == "__main__":  # pragma: no cover
    app()
