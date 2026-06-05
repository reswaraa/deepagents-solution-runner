# Service Catalog (Mock)

| Service        | Tier | Owner team                  | Escalation group              |
|----------------|------|-----------------------------|-------------------------------|
| payment-api    | 1    | Payments Platform           | payments-platform-oncall      |
| login-service  | 1    | Identity Platform           | identity-platform-oncall      |
| data-pipeline  | 2    | Data Platform               | data-platform-oncall          |
| billing-api    | 2    | Billing Platform            | billing-platform-oncall       |
| static-site    | 4    | Marketing Eng               | marketing-eng-oncall          |

## Notification channels

| Channel              | Purpose                                 | Allowed sevs |
|----------------------|-----------------------------------------|--------------|
| #incident-room       | Active incident coordination            | SEV-1..4     |
| #status-public       | Customer-visible status updates         | SEV-1, SEV-2 |
| #ops-noise           | Low-priority noise / FYI                | SEV-3, SEV-4 |

Any service or channel not in this catalog should be treated as
**unknown** and never escalated to or notified.
