# Root Cause Analysis Report
**Date:** 2026-04-28 09:55 UTC
**Incident:** RDS connection pool exhausted — 503 errors on all API endpoints at 09:15 UTC
**Severity:** P1 — Full outage, all endpoints returning 503
**Duration:** 09:15 – 09:48 UTC (33 minutes)

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:50 | Marketing campaign email sent — traffic spike begins |
| 09:00 | Active connections climb from 120 → 400 |
| 09:10 | Active connections reach 750 (83% of max_connections=900) |
| 09:15 | `rds-connections-high` alarm fires (connections = 912, exceeds max) |
| 09:15 | New connection attempts fail: `FATAL: remaining connection slots reserved for non-replication superuser` |
| 09:16 | App servers begin returning 503 — connection pool wait timeout exceeded |
| 09:20 | On-call paged |
| 09:30 | RDS Proxy enabled, absorbing connection spikes |
| 09:48 | Connections stabilise at 180 via proxy pooling, 503s stop |

---

## Findings

### CloudWatch Alarms
- `rds-connections-high` — DatabaseConnections Maximum > 900 (peaked at 912)
- `prod-api-high-latency` — ALB latency > 2s (secondary effect)

### Log Analysis (`/aws/rds/prod-aurora`, filter: ERROR)
```
FATAL:  remaining connection slots reserved for non-replication superuser connections
ERROR:  could not connect to server: Connection refused
WARN:   HikariPool-1 - Connection is not available, request timed out after 30000ms
ERROR:  Unable to acquire JDBC Connection
```

### Metric Stats (RDS DatabaseConnections, last 2h)
| Time  | Max Connections |
|-------|----------------|
| 08:00 | 118            |
| 08:50 | 120            |
| 09:00 | 400            |
| 09:10 | 750            |
| 09:15 | 912            |
| 09:30 | 210 (proxy)    |
| 09:48 | 180            |

### Recent Deployments
- No deployments in last 24h

### CloudTrail Events
- No infrastructure changes in last 2h

---

## Root Cause

**Traffic spike from marketing campaign overwhelmed the connection pool.**

The `items-api` application uses HikariCP with `maximumPoolSize=50` per pod. With 18 ECS tasks running, the theoretical max connections = 18 × 50 = **900**, exactly matching `max_connections` on the RDS instance. No headroom existed for admin connections or connection overhead.

When the marketing email drove a 3x traffic spike, ECS auto-scaling launched new tasks — each opening 50 new connections — pushing total connections over the limit before the new tasks were healthy enough to serve traffic.

There was no RDS Proxy in place to pool and multiplex connections.

---

## Recommendations

### Immediate (done)
- [x] Enabled RDS Proxy — reduced effective connections to ~180

### Short-term
1. **Reduce HikariCP pool size:** Set `maximumPoolSize=10` per pod. With RDS Proxy, large per-pod pools are unnecessary.
2. **Set `max_connections` headroom:** Reserve 10% for admin: `max_connections = floor(pod_count × pool_size × 0.9)`.
3. **Alert earlier:** Change alarm threshold to 70% of max_connections (630) instead of 100%.

### Long-term
4. **RDS Proxy as standard:** Make RDS Proxy mandatory for all production Aurora clusters.
5. **Load test marketing campaigns:** Coordinate with marketing to run load tests before large email sends.
6. **Connection pool monitoring:** Add HikariCP metrics to CloudWatch (pool size, wait time, timeout count).
