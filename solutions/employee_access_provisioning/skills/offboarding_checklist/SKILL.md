---
name: offboarding-checklist
description: Use this skill when processing an offboarding access revocation request. Ensures all systems are revoked within SLA, with special urgency for tier-3 finance and security systems.
---

# Offboarding Checklist Skill

Follow this process for every offboarding request:

1. Read the request with `get_access_request`. Note the employee's last
   working day.
2. Calculate urgency:
   - If last day is today or already past → treat as urgent, all SLAs active.
   - Finance/HR systems (tier-3): must be revoked within 4 hours.
   - All other systems: must be revoked within 24 hours.
3. Search `search_system_catalog` for each system to be revoked to confirm
   tier and revocation SLA.
4. Check `search_provisioning_history` for any prior offboarding patterns
   for this department or role.
5. Draft the revocation with `draft_access_change`, listing every system
   and the reason.
6. For any tier-3 system revocation, recommend notifying the security team
   via `notify_team` to `#security-ops`.
7. Call `revoke_access` (requires human approval) with the full list of systems.
8. In your final answer, state explicitly which systems were revoked, which
   are still pending, and whether the SLA has been met.
9. Never claim a system was revoked unless `revoke_access` returned
   `status: success` for that system.
