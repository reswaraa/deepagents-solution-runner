---
name: escalation-policy
description: Use this skill when deciding whether and how to escalate an IT incident to a specific oncall group.
---

# Escalation Policy Skill

Escalate only when:

- SEV-1 or SEV-2 symptoms persist for more than 15 minutes, OR
- a Tier-1 service is breaching its SLO, OR
- the on-call human has explicitly requested escalation.

Routing (from `service_catalog`):

| Service        | Escalation group              |
|----------------|-------------------------------|
| payment-api    | payments-platform-oncall      |
| login-service  | identity-platform-oncall      |
| data-pipeline  | data-platform-oncall          |
| billing-api    | billing-platform-oncall       |

Never escalate to a group that is not listed in the service catalog.
Never escalate without first attaching a diagnosis via
`update_ticket` (with approval).
