# IT Incident Resolution SOP (Mock)

> This is a **fake** SOP used for prototype testing. It contains no real
> internal procedures and no real system names.

## Section 1 — Severity classification

| Severity | Definition                                       | SLA response |
|----------|--------------------------------------------------|--------------|
| SEV-1    | Customer-impacting outage of a Tier-1 service.   | 15 min       |
| SEV-2    | Significant degradation; SLA at risk.            | 30 min       |
| SEV-3    | Minor degradation; no SLA breach.                | 4 hours      |
| SEV-4    | Cosmetic / internal-only issue.                  | 1 business day |

## Section 2 — Investigation order

1. Read the ticket details.
2. Identify the affected service and current status.
3. Pull the last 30 minutes of related alerts (mock: assume present).
4. Search the SOP for the specific symptom class.
5. Search similar historical incidents.
6. Form a hypothesis with at least one cited reference.

## Section 3 — Escalation policy

- Escalate to the service owner if symptoms persist for more than
  **15 minutes** on a SEV-1 or SEV-2.
- Escalate to **payments-platform-oncall** for any Payment API issue
  that breaches latency or error-rate SLO.
- Escalate to **identity-platform-oncall** for login or auth issues.
- Escalate to **data-platform-oncall** for pipeline / batch delays.
- Never escalate without first attaching the diagnosis to the ticket
  via `update_ticket` (with approval).

## Section 4 — Ticket update policy

- Every update must include:
  - current severity
  - symptom summary
  - investigation evidence (SOP section or historical incident id)
  - proposed next action
- Empty or content-free comments are not allowed.
- Updates are not posted until a human approves.

## Section 5 — Notification policy

- Use `#incident-room` for active incident coordination.
- Use `#status-public` only for customer-visible status changes; this
  channel requires a SEV-1 or SEV-2 confirmed by the on-call lead.
- Never notify on speculation.

## Section 6 — Closing an incident

- An incident may only be closed once:
  - the service is back within SLO, and
  - a postmortem ticket has been opened.
- Closing is out of scope for the copilot — humans only.
