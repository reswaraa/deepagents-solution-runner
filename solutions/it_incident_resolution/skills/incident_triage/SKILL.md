---
name: incident-triage
description: Use this skill when investigating an IT incident, diagnosing likely cause, identifying severity, and recommending the next action.
---

# Incident Triage Skill

Follow this process when you receive an incident-related request:

1. Read the ticket details using `get_ticket`.
2. Identify the affected service, severity, status, and symptoms.
3. Search the incident SOP using `search_sop`.
4. Search similar historical incidents using `search_similar_incidents`.
5. Compare current symptoms with past cases.
6. Recommend one of: monitor, request more information, escalate,
   update ticket, notify team.
7. Explain the business reason and risk.
8. Never claim that an update, escalation, or notification happened
   unless the corresponding tool returned `status: success`.
