---
name: ticket-update-drafting
description: Use this skill when drafting a ticket update comment that will later require human approval before being posted.
---

# Ticket Update Drafting Skill

Required structure for any ticket update:

1. **Current severity** (e.g., SEV-2).
2. **Symptom summary** in one sentence.
3. **Investigation evidence** — quote the relevant SOP section or
   reference at least one similar historical incident id.
4. **Proposed next action** with risk assessment.
5. **Owner / escalation group** if escalation is being recommended.

Rules:

- Never produce an empty update comment.
- Use `draft_ticket_update` to compose the text before calling
  `update_ticket`.
- Do not call `update_ticket` until the draft is ready; the call will
  be intercepted for human approval.
