# Employee Access Control Policy (Mock)

> This is a **fake** policy document used for prototype testing. It contains
> no real internal procedures and no real system names.

## Section 1 — Access tiers

| Tier | Classification | Examples                                 | Approval required        |
|------|---------------|------------------------------------------|--------------------------|
| 1    | Public-internal| Slack, Jira, email, intranet             | Manager only             |
| 2    | Internal       | GitHub org, VPN, Datadog, Confluence     | Manager + IT ops         |
| 3    | Sensitive      | AWS console (prod), Kubernetes (prod),   | Manager + IT ops + CISO  |
|      |               | finance-reporting, SAP HANA              | review                   |
| 4    | Critical       | Production DB direct access, HSM access  | CISO written approval    |

Tier-3 and tier-4 access must never be provisioned on the same day as the
request without explicit written approval from the CISO.

## Section 2 — Onboarding access policy

- Every new employee receives tier-1 systems on day 1 as standard.
- Tier-2 systems are granted within 2 business days on manager approval.
- Tier-3 and above require a separate access justification form and
  CISO review before provisioning.
- Contractors receive tier-1 access only unless a named exception is filed.

## Section 3 — Role-change access policy

- When an employee changes role, existing access that no longer applies to
  the new role **must be revoked** before new access is granted.
- The manager of the new role is responsible for submitting the request.
- Tier-3 access for a new role requires a fresh CISO review even if the
  employee previously held equivalent access.
- Role-change requests must be processed within 5 business days of the
  effective date.

## Section 4 — Offboarding access policy

- All system access must be revoked within **24 hours** of the employee's
  last working day.
- Finance and HR systems (tier-3) must be revoked within **4 hours**.
- The IT ops team is responsible for verifying revocation via the system
  catalog owner for each tier-3 system.
- If revocation cannot be completed within the SLA, escalate to the
  security team immediately via `notify_team` to `#security-ops`.

## Section 5 — Privileged access rules

- `aws-console-prod` and `kubernetes-dashboard-prod` are tier-3 systems.
  Access requires MFA enrollment and manager + CISO approval.
- `sap-hana` and `finance-reporting` are tier-3. The CFO must be notified
  of any new grant or revocation affecting finance personnel.
- Any access to tier-4 systems must be logged as a formal change record
  with a business justification and approved by the CISO in writing.
- Shared or generic accounts are prohibited for tier-3 and above.

## Section 6 — Audit and review

- All provisioning and revocation events must be logged with the request ID,
  employee ID, system name, and operator ID.
- Quarterly access reviews are conducted by the security team. Unexplained
  tier-2+ access will be revoked automatically.
- Unresolved offboarding requests older than 48 hours are escalated to CISO.
