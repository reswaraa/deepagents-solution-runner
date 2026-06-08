# Internal System Catalog (Mock)

> Fake catalog used for prototype testing only.

## Tier-1 Systems (Public-internal)

### Slack
- **id**: slack
- **tier**: 1
- **owner**: it-ops
- **provisioning**: automatic on onboarding request approval
- **revocation SLA**: 24 hours

### Jira
- **id**: jira
- **tier**: 1
- **owner**: it-ops
- **provisioning**: automatic on onboarding request approval
- **revocation SLA**: 24 hours

### IT Helpdesk Portal
- **id**: it-helpdesk-portal
- **tier**: 1
- **owner**: it-ops
- **provisioning**: IT support role only
- **revocation SLA**: 24 hours

## Tier-2 Systems (Internal)

### GitHub Organisation
- **id**: github-org
- **tier**: 2
- **owner**: engineering-platform
- **provisioning**: manager approval + IT ops
- **revocation SLA**: 24 hours
- **notes**: All engineers. Contractors require named exception.

### VPN (Basic)
- **id**: vpn-basic
- **tier**: 2
- **owner**: network-ops
- **provisioning**: manager approval + IT ops
- **revocation SLA**: 24 hours

### Datadog
- **id**: datadog
- **tier**: 2
- **owner**: observability-team
- **provisioning**: manager approval + IT ops
- **revocation SLA**: 24 hours
- **notes**: DevOps and SRE roles standard. Other roles require justification.

### Confluence
- **id**: confluence
- **tier**: 2
- **owner**: it-ops
- **provisioning**: manager approval + IT ops
- **revocation SLA**: 24 hours

## Tier-3 Systems (Sensitive)

### AWS Console (Production)
- **id**: aws-console-prod
- **tier**: 3
- **owner**: cloud-platform
- **provisioning**: manager + IT ops + CISO review; MFA enrollment required
- **revocation SLA**: 4 hours
- **escalation-group**: cloud-platform-oncall
- **notes**: DevOps and platform engineering roles only.

### Kubernetes Dashboard (Production)
- **id**: kubernetes-dashboard-prod
- **tier**: 3
- **owner**: cloud-platform
- **provisioning**: manager + IT ops + CISO review; MFA enrollment required
- **revocation SLA**: 4 hours
- **escalation-group**: cloud-platform-oncall

### Finance Reporting
- **id**: finance-reporting
- **tier**: 3
- **owner**: finance-it
- **provisioning**: manager + IT ops + CFO notification
- **revocation SLA**: 4 hours
- **escalation-group**: finance-it-oncall
- **notes**: Finance team only.

### SAP HANA
- **id**: sap-hana
- **tier**: 3
- **owner**: finance-it
- **provisioning**: manager + IT ops + CISO written approval + CFO notification
- **revocation SLA**: 4 hours
- **escalation-group**: finance-it-oncall
- **notes**: Finance Analysts and above only.
