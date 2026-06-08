---
name: access-review
description: Use this skill when reviewing an access provisioning request — onboarding, role change, or ad-hoc access grant. Covers policy lookup, tier assessment, and draft preparation.
---

# Access Review Skill

Follow this process when you receive an access provisioning request:

1. Read the full request with `get_access_request`.
2. Identify: request type, employee role, department, and systems requested.
3. Search `search_access_policy` for the section covering this request type
   (Section 2 for onboarding, Section 3 for role change).
4. For each system requested, search `search_system_catalog` to confirm:
   - tier
   - owner team
   - special approval requirements
5. Classify the overall risk:
   - All tier-1/2 → standard, proceed with manager approval.
   - Any tier-3 → flag for CISO review, do not provision same day.
   - Any tier-4 → block and escalate immediately.
6. Use `search_provisioning_history` to find similar past requests and
   check if any caveats or delays are expected.
7. Draft the change with `draft_access_change`.
8. Present your recommendation clearly before calling any action tool.
9. Never claim access was granted unless `grant_access` returned `status: success`.
