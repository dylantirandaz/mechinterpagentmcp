# Billing service runbook

- Restart: `systemctl restart billing`
- Logs: `/var/log/billing/`
- Escalation: page the on-call engineer via the pager rota.

If the service is down, check the database connection first.
