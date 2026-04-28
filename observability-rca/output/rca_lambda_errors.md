# Root Cause Analysis Report
**Date:** 2026-04-28 15:10 UTC
**Incident:** Lambda `items-api` error rate 15% at 14:30 UTC
**Severity:** P2 — Partial degradation, write operations failing
**Duration:** 14:30 – 14:52 UTC (22 minutes)

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:15 | Deploy pushed — Lambda memory reduced from 1024MB to 128MB (cost optimisation PR) |
| 14:30 | Lambda `Errors` alarm fires — error count > 5 per minute |
| 14:31 | CloudWatch logs show `Task timed out after 3.00 seconds` |
| 14:35 | On-call paged |
| 14:48 | Memory reverted to 1024MB via console |
| 14:52 | Error rate drops to 0%, alarm resolves |

---

## Findings

### CloudWatch Alarms
- `lambda-errors` — Lambda Errors Sum > 5 (firing since 14:30)

### Log Analysis (`/aws/lambda/items-api`, filter: ERROR)
```
START RequestId: a1b2c3 Version: $LATEST
ERROR: Task timed out after 3.00 seconds
START RequestId: d4e5f6 Version: $LATEST
INIT_START Runtime Version: python:3.12
ERROR: Task timed out after 3.00 seconds
REPORT Duration: 3000ms  Billed: 3000ms  Memory Size: 128MB  Max Memory Used: 127MB
```

### Metric Stats (Lambda Duration, last 60 min)
| Time  | Avg Duration | Max Duration |
|-------|-------------|-------------|
| 14:00 | 180ms       | 420ms       |
| 14:30 | 2,800ms     | 3,000ms     |
| 14:35 | 3,000ms     | 3,000ms     |
| 14:52 | 190ms       | 380ms       |

### CloudTrail Events (resource: items-api, last 2h)
- `14:15` — `UpdateFunctionConfiguration` by `ci-deploy-role` — MemorySize: 1024 → 128

---

## Root Cause

The deploy at 14:15 reduced Lambda memory from **1024MB to 128MB**.

AWS Lambda allocates CPU proportionally to memory. At 128MB, the function received ~8% of a vCPU vs ~80% at 1024MB. The `items-api` handler calls DynamoDB and performs JSON serialisation — operations that are CPU-bound. With 10x less CPU, execution time exceeded the 3-second timeout, causing all invocations to fail.

The `Max Memory Used: 127MB` in logs confirms the function was also memory-constrained, compounding the CPU throttle.

---

## Recommendations

### Immediate (done)
- [x] Reverted Lambda memory to 1024MB at 14:48

### Short-term
1. **Set memory floor in CI:** Add a check that prevents memory < 512MB for functions with DynamoDB/external calls.
2. **Add duration alarm:** `Duration p99 > 2000ms` to catch slowdowns before they hit the timeout.
3. **Cost optimisation process:** Use AWS Lambda Power Tuning tool to find the optimal memory — don't reduce blindly.

### Long-term
4. **Canary deployments for Lambda:** Use Lambda weighted aliases to route 5% traffic to new version before full rollout.
5. **Automated rollback:** Configure CodeDeploy Lambda deployment with `LambdaCanary10Percent5Minutes` + CloudWatch alarm rollback trigger.
