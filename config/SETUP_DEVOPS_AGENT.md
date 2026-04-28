# AWS DevOps Agent Setup (Observability + Root Cause Analysis)

## What It Covers
- Autonomous incident investigation across AWS, Azure, on-prem
- Root cause analysis correlating logs, metrics, traces, code, deployments
- Proactive recommendations for observability, infrastructure, pipelines

## Prerequisites
- AWS account with AWS Support plan (DevOps Agent included)
- IAM permissions for DevOps Agent
- Observability tools (CloudWatch, Azure Monitor, Datadog, etc.)

## Setup Steps

### 1. Enable AWS DevOps Agent
```bash
# Via AWS Console
# Navigate to: AWS DevOps Agent → Create Agent Space
# Or via CLI:
aws devops-agent create-agent-space \
  --name "production-ops" \
  --description "Hybrid cloud observability"
```

### 2. Configure IAM Role
Create role with trust policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "devops-agent.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
```

Attach managed policy:
```bash
aws iam attach-role-policy \
  --role-name DevOpsAgentRole \
  --policy-arn arn:aws:iam::aws:policy/AWSDevOpsAgentFullAccess
```

### 3. Connect Observability Tools via MCP

#### CloudWatch (AWS)
```bash
# Auto-configured if using AWS resources
# Enable CloudWatch Logs Insights:
aws logs put-resource-policy \
  --policy-name DevOpsAgentAccess \
  --policy-document file://cloudwatch-policy.json
```

#### Azure Monitor (Azure workloads)
```bash
# Install Azure Monitor MCP
uvx awslabs.azure-monitor-mcp-server@latest

# Configure in Agent Space:
aws devops-agent add-mcp-server \
  --agent-space-id <space-id> \
  --server-name azure-monitor \
  --server-config file://azure-mcp-config.json
```

Example `azure-mcp-config.json`:
```json
{
  "command": "uvx",
  "args": ["awslabs.azure-monitor-mcp-server@latest"],
  "env": {
    "AZURE_SUBSCRIPTION_ID": "<subscription-id>",
    "AZURE_TENANT_ID": "<tenant-id>"
  }
}
```

#### On-Premises (Prometheus/Grafana)
```bash
# Install Prometheus MCP
uvx prometheus-mcp-server@latest

# Configure:
aws devops-agent add-mcp-server \
  --agent-space-id <space-id> \
  --server-name prometheus \
  --server-config file://prometheus-mcp-config.json
```

Example `prometheus-mcp-config.json`:
```json
{
  "command": "uvx",
  "args": ["prometheus-mcp-server@latest"],
  "env": {
    "PROMETHEUS_URL": "http://prometheus.internal:9090"
  }
}
```

### 4. Connect CI/CD Pipelines
```bash
# GitHub
aws devops-agent connect-repository \
  --agent-space-id <space-id> \
  --repo-url https://github.com/org/repo \
  --token-secret-arn arn:aws:secretsmanager:region:account:secret:github-token

# GitLab
aws devops-agent connect-repository \
  --agent-space-id <space-id> \
  --repo-url https://gitlab.com/org/repo \
  --token-secret-arn arn:aws:secretsmanager:region:account:secret:gitlab-token

# Azure DevOps
aws devops-agent connect-repository \
  --agent-space-id <space-id> \
  --repo-url https://dev.azure.com/org/project/_git/repo \
  --token-secret-arn arn:aws:secretsmanager:region:account:secret:ado-token
```

### 5. Configure Alerting Integrations
```bash
# Slack
aws devops-agent add-notification-channel \
  --agent-space-id <space-id> \
  --channel-type slack \
  --webhook-url-secret-arn arn:aws:secretsmanager:region:account:secret:slack-webhook

# PagerDuty
aws devops-agent add-notification-channel \
  --agent-space-id <space-id> \
  --channel-type pagerduty \
  --integration-key-secret-arn arn:aws:secretsmanager:region:account:secret:pagerduty-key
```

### 6. Test Investigation
```bash
# Trigger manual investigation
aws devops-agent start-investigation \
  --agent-space-id <space-id> \
  --description "High CPU on prod-api-server" \
  --resource-ids i-1234567890abcdef0
```

Or via web UI: https://console.aws.amazon.com/devops-agent

## Usage Patterns

### Autonomous Mode
DevOps Agent automatically investigates when:
- CloudWatch alarms fire
- PagerDuty incidents created
- Slack mentions @devops-agent

### Interactive Mode
Chat with agent in DevOps Agent Space:
```
User: "Why is prod-api latency spiking?"
Agent: [Correlates metrics, logs, recent deployments]
       "Latency increased 300ms after deploy abc123.
        Root cause: New DB query missing index on orders.user_id.
        Recommendation: Add index or rollback deploy."
```

### Proactive Recommendations
Weekly reports on:
- Missing observability (no alarms on critical resources)
- Infrastructure optimization (underutilized instances)
- Pipeline improvements (flaky tests, slow builds)

## Cost
- Included with AWS Support plans (Developer, Business, Enterprise)
- No additional charge for investigations
- MCP server compute billed separately (minimal)

## References
- [DevOps Agent Docs](https://docs.aws.amazon.com/devopsagent/latest/userguide/)
- [MCP Server Configuration](https://docs.aws.amazon.com/devopsagent/latest/userguide/configuring-capabilities-for-aws-devops-agent-connecting-mcp-servers.html)
