"""
Sample incident scenarios for the Observability / RCA Agent.
Each entry is a dict you can pass directly to agent() or use in tests.

Usage:
    from samples.incidents import INCIDENTS
    agent = build_agent()
    agent(INCIDENTS["high_latency"]["prompt"])
"""

INCIDENTS = {

    # ── 1. High API latency ───────────────────────────────────────────────────
    "high_latency": {
        "title": "prod-api p99 latency spike",
        "prompt": (
            "Investigate this incident: prod-api p99 latency jumped from 120ms to 8500ms at 10:00 UTC.\n"
            "Log group: /aws/ecs/prod-api\n"
            "Resource: prod-aurora-cluster\n"
            "Region: us-east-1\n"
            "Write the RCA report to: output/rca_high_latency.md"
        ),
        "expected_signals": ["ALB latency alarm", "RDS CPU", "recent deployment", "DB query"],
    },

    # ── 2. Lambda error rate spike ────────────────────────────────────────────
    "lambda_errors": {
        "title": "Lambda items-api error rate 15%",
        "prompt": (
            "Investigate this incident: Lambda function items-api error rate jumped to 15% at 14:30 UTC.\n"
            "Log group: /aws/lambda/items-api\n"
            "Resource: items-api\n"
            "Region: us-east-1\n"
            "Write the RCA report to: output/rca_lambda_errors.md"
        ),
        "expected_signals": ["Lambda Errors alarm", "timeout", "cold start", "memory"],
    },

    # ── 3. RDS connection pool exhaustion ─────────────────────────────────────
    "rds_connections": {
        "title": "RDS connection pool exhausted",
        "prompt": (
            "Investigate this incident: prod-rds DatabaseConnections hit max_connections (900) at 09:15 UTC, "
            "causing 503 errors on all API endpoints.\n"
            "Log group: /aws/rds/prod-aurora\n"
            "Resource: prod-aurora-cluster\n"
            "Region: us-east-1\n"
            "Write the RCA report to: output/rca_rds_connections.md"
        ),
        "expected_signals": ["DatabaseConnections alarm", "connection pool", "max_connections", "deployment"],
    },

    # ── 4. ECS service crash loop ─────────────────────────────────────────────
    "ecs_crash_loop": {
        "title": "ECS tasks restarting repeatedly",
        "prompt": (
            "Investigate this incident: ECS service prod-api tasks are crash-looping — "
            "DesiredCount=3 but RunningCount oscillates between 0 and 1 since 08:00 UTC.\n"
            "Log group: /aws/ecs/prod-api\n"
            "Resource: prod-cluster\n"
            "Region: us-east-1\n"
            "Write the RCA report to: output/rca_ecs_crash_loop.md"
        ),
        "expected_signals": ["OOMKilled", "health check", "container exit", "memory limit"],
    },

    # ── 5. Deployment-triggered regression ────────────────────────────────────
    "deploy_regression": {
        "title": "5xx errors after deploy",
        "prompt": (
            "Investigate this incident: ALB 5xx error rate went from 0% to 12% immediately after "
            "deploy d-XYZ789 at 16:00 UTC. No infrastructure changes.\n"
            "Log group: /aws/ecs/prod-api\n"
            "Resource: prod-api-alb\n"
            "Region: us-east-1\n"
            "Write the RCA report to: output/rca_deploy_regression.md"
        ),
        "expected_signals": ["5xx alarm", "deploy d-XYZ789", "NullPointerException", "rollback"],
    },

}
