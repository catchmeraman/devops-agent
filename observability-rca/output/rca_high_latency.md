# Root Cause Analysis Report
**Date:** 2026-04-28 10:45 UTC
**Incident:** prod-api p99 latency spike — 120ms → 8500ms at 10:00 UTC
**Severity:** P1 — Customer-facing, all API endpoints affected
**Duration:** 10:00 – 10:38 UTC (38 minutes)

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 08:40 | RDS parameter group `prod-pg-params` modified by `ops-engineer` (disabled `query_cache_size`) |
| 08:45 | Deploy `d-ABC123` pushed to ECS service `prod-api` (added `/api/v1/orders/summary` endpoint) |
| 10:00 | ALB `TargetResponseTime` p99 crosses 2s threshold → alarm fires |
| 10:02 | RDS `CPUUtilization` alarm fires (CPU at 94%) |
| 10:05 | `/aws/ecs/prod-api` logs show `ERROR: Query timeout on orders table` |
| 10:12 | On-call engineer paged via PagerDuty |
| 10:25 | Index added: `CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id)` |
| 10:38 | Latency returns to baseline (p99 = 130ms), alarms resolve |

---

## Findings

### CloudWatch Alarms (ALARM state at 10:00 UTC)
- `prod-api-high-latency` — ALB TargetResponseTime p99 > 2000ms
- `prod-rds-cpu-high` — RDS CPUUtilization > 90% (peaked at 94%)

### Log Analysis (`/aws/ecs/prod-api`, last 30 min, filter: ERROR)
```
ERROR: Query timeout on orders table - missing index on user_id (30s timeout)
ERROR: Connection pool exhausted after 30s timeout
WARN:  Retry attempt 3/3 for DB connection
ERROR: 500 Internal Server Error - /api/v1/orders/summary
```

### Metric Spike (ALB TargetResponseTime)
| Time  | p99 Latency |
|-------|-------------|
| 09:55 | 120ms       |
| 10:00 | 850ms       |
| 10:05 | 3,200ms     |
| 10:10 | 8,500ms     |
| 10:35 | 140ms       |

### Recent Deployments (last 24h)
- `d-ABC123` — app: `prod-api`, group: `prod-api-group`, status: Succeeded, created: 08:45 UTC

### CloudTrail Events (last 2h, resource: prod-aurora-cluster)
- `08:40` — `ModifyDBParameterGroup` by `ops-engineer` (rds.amazonaws.com)
- `08:45` — `UpdateService` by `ci-deploy-role` (ecs.amazonaws.com)

---

## Root Cause

**Two compounding changes within 20 minutes caused the incident:**

1. **RDS parameter change (08:40):** `ops-engineer` disabled `query_cache_size` in the RDS parameter group, removing query result caching for the `orders` table.

2. **Deploy d-ABC123 (08:45):** Introduced a new endpoint `/api/v1/orders/summary` that runs a `SELECT ... WHERE user_id = ?` query on the `orders` table. This column had no index.

With caching disabled and no index, every request to the new endpoint triggered a full table scan on `orders` (~12M rows). Under normal traffic (800 req/min), this saturated RDS CPU and caused query timeouts, which cascaded into connection pool exhaustion and 500 errors across all endpoints.

---

## Recommendations

### Immediate (done)
- [x] Added index: `CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id)`
- [x] Latency resolved at 10:38 UTC

### Short-term (within 24h)
1. **Re-enable query cache:** Revert `query_cache_size` to previous value or evaluate if the change was intentional.
2. **Add query analysis to CI:** Run `EXPLAIN ANALYZE` on new queries in the build pipeline — fail if full table scan detected.
3. **Lower connection pool timeout:** Reduce from 30s to 5s to fail fast and shed load sooner.

### Long-term
4. **Pre-deploy load test:** Run k6/Locust against staging with production-scale data before merging.
5. **RDS Performance Insights:** Enable and alert on `db.load.avg > 5` to catch slow queries earlier.
6. **Change management:** Require approval for RDS parameter group changes during business hours.
7. **Alarm on p95 latency:** Current alarm is p99 — add p95 > 500ms for earlier warning.
