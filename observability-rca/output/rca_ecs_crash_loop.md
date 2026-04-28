# Root Cause Analysis Report
**Date:** 2026-04-28 08:45 UTC
**Incident:** ECS service `prod-api` crash-looping — RunningCount oscillating 0–1 since 08:00 UTC
**Severity:** P1 — Service effectively down, DesiredCount=3 but RunningCount never stable
**Duration:** 08:00 – 08:42 UTC (42 minutes)

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 07:55 | Deploy `d-DEF456` pushed — updated task definition with new image |
| 08:00 | ECS begins replacing tasks with new task definition |
| 08:01 | New tasks start, pass initial health check, then crash after ~45s |
| 08:02 | ECS restarts tasks — crash loop begins |
| 08:05 | ALB health check failures → target group shows 0 healthy targets |
| 08:08 | On-call paged (ALB 5xx alarm) |
| 08:20 | Engineer identifies OOMKilled in logs |
| 08:35 | Task definition updated: memory 256MB → 1024MB |
| 08:42 | Tasks stable, RunningCount=3, health checks passing |

---

## Findings

### CloudWatch Alarms
- `alb-5xx-errors` — HTTPCode_ELB_5XX_Count > 10 (firing from 08:05)
- `ecs-memory-high` — MemoryUtilization > 85% (briefly, before OOM kill)

### Log Analysis (`/aws/ecs/prod-api`, filter: ERROR)
```
Starting application server...
Loading ML model weights from S3... (model size: 780MB)
ERROR: Container killed due to memory limit exceeded
WARN:  Task stopped with exit code 137 (OOMKilled)
Starting application server...
Loading ML model weights from S3...
ERROR: Container killed due to memory limit exceeded
```

### ECS Events (via CloudTrail)
```
StopTask: exit code 137 (OOMKilled) — task prod-api:47
StopTask: exit code 137 (OOMKilled) — task prod-api:48
StopTask: exit code 137 (OOMKilled) — task prod-api:49
```

### Recent Deployments
- `d-DEF456` — app: `prod-api`, status: InProgress (never completes), created: 07:55 UTC

### CloudTrail Events (resource: prod-cluster, last 2h)
- `07:55` — `RegisterTaskDefinition` by `ci-deploy-role` — memory: 256 → 256 (unchanged), new image tag

---

## Root Cause

**The new Docker image introduced an ML model that requires 780MB of memory, but the ECS task definition had a 256MB memory limit.**

The previous image did not load any ML model. The new image (tagged `v2.4.0`) added an on-startup model load from S3 (`/app/models/classifier.pkl`, 780MB). The task definition memory limit was never updated from the original 256MB.

Every container started, began loading the model, hit the 256MB limit, and was OOMKilled (exit code 137). ECS interpreted this as a failed health check and restarted the task — creating an infinite crash loop.

---

## Recommendations

### Immediate (done)
- [x] Updated task definition memory: 256MB → 1024MB
- [x] Tasks stable at 08:42

### Short-term
1. **Add memory requirement to PR checklist:** Any PR adding large assets (models, JARs, datasets) must update task definition memory.
2. **Fail CI on OOM:** Add a `docker run --memory=256m` smoke test in the build pipeline — if the container exits 137, fail the build.
3. **Lazy-load models:** Load ML models on first request, not at startup, to reduce startup memory pressure.

### Long-term
4. **Container right-sizing:** Use CloudWatch Container Insights `MemoryUtilized` to set memory limits at p99 + 20% headroom.
5. **ECS deployment circuit breaker:** Enable `DeploymentCircuitBreaker` with `rollback: true` — would have auto-rolled back to previous task definition after 3 failed tasks.
6. **Staging memory parity:** Ensure staging task definitions match production memory limits.
