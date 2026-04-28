# Root Cause Analysis Report
**Date:** 2026-04-28 16:20 UTC
**Incident:** ALB 5xx error rate 0% → 12% immediately after deploy `d-XYZ789` at 16:00 UTC
**Severity:** P2 — 12% of requests failing, no infrastructure changes
**Duration:** 16:00 – 16:18 UTC (18 minutes)

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 15:58 | Deploy `d-XYZ789` starts — new image `prod-api:v3.1.0` |
| 16:00 | Deploy completes, ECS tasks running new image |
| 16:00 | ALB `5xx` alarm fires — HTTPCode_Target_5XX_Count spikes |
| 16:01 | Error logs show `NullPointerException` in `OrderService.getDiscount()` |
| 16:05 | On-call paged |
| 16:10 | Engineer identifies missing env var `DISCOUNT_SERVICE_URL` |
| 16:15 | Env var added to task definition, redeploy triggered |
| 16:18 | 5xx rate drops to 0%, alarm resolves |

---

## Findings

### CloudWatch Alarms
- `alb-5xx-errors` — HTTPCode_ELB_5XX_Count > 10 (firing from 16:00)
- `alb-high-latency` — NOT firing (latency normal — only affected endpoints failing fast)

### Log Analysis (`/aws/ecs/prod-api`, filter: ERROR)
```
ERROR: NullPointerException at OrderService.getDiscount(OrderService.java:142)
ERROR: DISCOUNT_SERVICE_URL environment variable is not set
ERROR: Failed to initialise DiscountClient — null URL
ERROR: 500 Internal Server Error - /api/v1/orders (NullPointerException)
ERROR: 500 Internal Server Error - /api/v1/cart/checkout (NullPointerException)
INFO:  /api/v1/products - 200 OK  (unaffected endpoint)
```

### Metric Stats (ALB HTTPCode_Target_5XX_Count, last 2h)
| Time  | 5xx Count (per min) |
|-------|---------------------|
| 15:55 | 0                   |
| 16:00 | 87                  |
| 16:02 | 94                  |
| 16:10 | 91                  |
| 16:18 | 0                   |

### Recent Deployments
- `d-XYZ789` — app: `prod-api`, status: Succeeded, created: 15:58 UTC

### CloudTrail Events (resource: prod-api-alb, last 2h)
- `15:58` — `UpdateService` by `ci-deploy-role` — new task definition revision 31

---

## Root Cause

**Deploy `d-XYZ789` introduced a new `DiscountService` integration that requires the environment variable `DISCOUNT_SERVICE_URL`, which was not added to the ECS task definition.**

The new code in `OrderService.java:142` calls `DiscountClient(System.getenv("DISCOUNT_SERVICE_URL"))`. When the env var is absent, `getenv()` returns `null`, causing a `NullPointerException` on every request to `/api/v1/orders` and `/api/v1/cart/checkout`. Endpoints that don't touch `OrderService` (e.g., `/api/v1/products`) were unaffected, explaining the 12% error rate rather than 100%.

The env var was present in the developer's local `.env` file and in staging (added manually), but was never added to the production task definition.

---

## Recommendations

### Immediate (done)
- [x] Added `DISCOUNT_SERVICE_URL` to ECS task definition
- [x] Redeployed at 16:15, resolved at 16:18

### Short-term
1. **Startup env var validation:** Add a startup check that validates all required env vars are present and non-null — fail fast with a clear error before serving traffic.
2. **Env var diff in PR:** Add a CI step that diffs required env vars between old and new image and fails if new vars are missing from the task definition.
3. **Staging parity check:** Automate a comparison of staging vs production task definition env vars before promoting a deploy.

### Long-term
4. **Centralised config management:** Use AWS AppConfig or Parameter Store for service configuration — eliminates the "forgot to add env var" class of bugs.
5. **Smoke test in pipeline:** Run a post-deploy smoke test hitting `/api/v1/orders` with a test order — would have caught this in 60 seconds.
6. **ECS deployment circuit breaker:** Enable with rollback — would have auto-rolled back after detecting 5xx spike, reducing MTTR from 18 min to ~3 min.
