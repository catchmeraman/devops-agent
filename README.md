# DevOps AI Agents

Three production-grade AI agents built with [Strands Agents](https://strandsagents.com) + **AWS Bedrock AgentCore** (Claude 3.5 Sonnet), each deployed as an independent AgentCore Runtime.

Part of the **AIEOS** ecosystem → [Intelligent_Event_Agent_with_AgentCore](https://github.com/catchmeraman/Intelligent_Event_Agent_with_AgentCore)

---

## Agents

| Agent | AgentCore Runtime | What it does |
|-------|------------------|-------------|
| **Jenkins Migration** | `jenkins_migration_agent` | Converts Jenkinsfiles → ADO / GitLab CI YAML |
| **IaC Generator** | `iac_generator_agent` | Generates CFN / Terraform / CDK from plain English |
| **Observability / RCA** | `observability_rca_agent` | Investigates incidents, writes structured RCA reports |

---

## Repository Structure

```
devops-agent/
├── .bedrock_agentcore.yaml           # AgentCore config for all 3 agents
├── deploy_all.sh                     # One-command deploy script
├── requirements.txt
│
├── jenkins-migration-agent/
│   ├── Dockerfile                    # AgentCore container
│   ├── agent.py                      # Strands agent
│   ├── test_migration.py
│   └── sample/
│       ├── Jenkinsfile
│       └── .gitlab-ci.yml
│
├── iac-generator/
│   ├── Dockerfile
│   ├── agent.py
│   ├── test_iac_generator.py
│   └── samples/                      # 7 ready-to-use IaC templates
│       ├── 01_vpc_with_nat.yaml
│       ├── 02_ecs_fargate_alb.yaml
│       ├── 03_rds_aurora/
│       ├── 04_serverless_api_cdk.py
│       ├── 05_codepipeline_ecs.yaml
│       ├── 06_s3_cloudfront.tf
│       └── 07_cloudwatch_alarms.yaml
│
└── observability-rca/
    ├── Dockerfile
    ├── agent.py
    ├── test_rca_agent.py
    ├── samples/
    │   └── incidents.py              # 5 sample incident prompts
    └── output/                       # 5 sample RCA reports
        ├── rca_high_latency.md
        ├── rca_lambda_errors.md
        ├── rca_rds_connections.md
        ├── rca_ecs_crash_loop.md
        └── rca_deploy_regression.md
```

---

## Prerequisites

```bash
# 1. AWS CLI v2 configured
aws sts get-caller-identity
# Expected: account 114805761158, region us-east-1

# 2. Python 3.12+
python3 --version

# 3. Docker (for container builds)
docker --version

# 4. AgentCore Starter Toolkit
pip install bedrock-agentcore-starter-toolkit strands-agents boto3 pyyaml

# 5. Bedrock model access — Claude 3.5 Sonnet must be enabled
# AWS Console → Amazon Bedrock → Model access → Anthropic Claude 3.5 Sonnet → Enable
```

---

## Setup (One-time)

### Step 1 — Clone

```bash
git clone https://github.com/catchmeraman/devops-agent.git
cd devops-agent
pip install -r requirements.txt
```

### Step 2 — Create ECR repositories

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

for name in jenkins_migration_agent iac_generator_agent observability_rca_agent; do
  aws ecr create-repository \
    --repository-name "bedrock-agentcore-${name}" \
    --region $REGION \
    --image-scanning-configuration scanOnPush=true
done
```

### Step 3 — Verify IAM role exists

The agents reuse the existing `event-agent-role` from AIEOS. Verify:

```bash
aws iam get-role --role-name event-agent-role \
  --query 'Role.Arn' --output text
# Expected: arn:aws:iam::114805761158:role/event-agent-role
```

If it doesn't exist, deploy it from the AIEOS repo first:
```bash
# In Intelligent_Event_Agent_with_AgentCore/
aws cloudformation deploy \
  --stack-name event-agent-core \
  --template-file infrastructure/agentcore-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides UserPoolArn=<cognito-arn> KnowledgeBaseId=<kb-id>
```

---

## Deployment

### Deploy all 3 agents (recommended)

```bash
bash deploy_all.sh all
```

### Deploy individually

```bash
bash deploy_all.sh jenkins   # Jenkins Migration Agent only
bash deploy_all.sh iac       # IaC Generator Agent only
bash deploy_all.sh rca       # Observability/RCA Agent only
```

### What the deploy script does (per agent)

```
1. ECR login
2. Create ECR repo (if missing)
3. docker build --platform linux/arm64
4. docker push → ECR
5. agentcore deploy → creates/updates AgentCore Runtime
```

### Verify deployment

```bash
aws bedrock-agentcore list-agent-runtimes --region us-east-1 \
  --query 'agentRuntimes[*].[agentRuntimeName,status,agentRuntimeArn]' \
  --output table
```

Expected:
```
-----------------------------------------------------------------------
| jenkins_migration_agent  | ACTIVE | arn:aws:bedrock-agentcore:... |
| iac_generator_agent      | ACTIVE | arn:aws:bedrock-agentcore:... |
| observability_rca_agent  | ACTIVE | arn:aws:bedrock-agentcore:... |
-----------------------------------------------------------------------
```

---

## Agent 1 — Jenkins Migration Agent

### STAR Summary

| | |
|---|---|
| **Situation** | Teams migrating from Jenkins to Azure DevOps or GitLab CI spend days manually rewriting pipelines, often missing plugin equivalents or post-build hooks. |
| **Task** | Automatically parse any Jenkinsfile and produce a correct, runnable pipeline YAML for the target platform. |
| **Action** | Parses stages, steps, env vars, triggers, and post hooks. Maps 10 Jenkins plugins (Maven, Docker, SonarQube, Terraform, etc.) to native ADO tasks or GitLab script commands. Flags unknown plugins as gaps. |
| **Result** | Complete `azure-pipelines.yml` or `.gitlab-ci.yml` in seconds, with a gap report for anything needing manual review. |

### Workflow

```
Jenkinsfile
    │
    ▼
parse_jenkinsfile()
    ├── stages / steps / env vars / triggers / post hooks
    │
    ▼
explain_migration_gaps()     ← flags unknown plugins
    │
    ▼
migrate_jenkinsfile()
    ├── to_ado()    → azure-pipelines.yml
    └── to_gitlab() → .gitlab-ci.yml
```

### Run locally

```bash
cd jenkins-migration-agent

python agent.py --jenkinsfile sample/Jenkinsfile --target gitlab
python agent.py --jenkinsfile sample/Jenkinsfile --target ado
python agent.py --jenkinsfile /path/to/your/Jenkinsfile --target gitlab
```

### Invoke via AgentCore Runtime

```bash
# Get the runtime ARN
RUNTIME_ARN=$(aws bedrock-agentcore list-agent-runtimes --region us-east-1 \
  --query 'agentRuntimes[?agentRuntimeName==`jenkins_migration_agent`].agentRuntimeArn' \
  --output text)

# Invoke
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $RUNTIME_ARN \
  --runtime-session-id "session-$(date +%s)" \
  --payload '{"prompt": "Migrate jenkins-migration-agent/sample/Jenkinsfile to gitlab"}' \
  --region us-east-1
```

### Test

```bash
python test_migration.py -v
# Ran 4 tests in 0.3s  OK
```

---

## Agent 2 — IaC Generator Agent

### STAR Summary

| | |
|---|---|
| **Situation** | Writing CloudFormation, Terraform, or CDK from scratch is slow and error-prone — engineers spend hours on boilerplate, IAM roles, and resource wiring. |
| **Task** | Generate complete, production-ready IaC from a single natural language description. |
| **Action** | Uses Claude 3.5 Sonnet to generate IaC, calls `write_iac_file()` to save it, and `validate_cloudformation()` to structurally verify CFN templates. |
| **Result** | A validated, deployable IaC file in seconds — CFN YAML, Terraform HCL (main + variables + outputs), or a full CDK app. |

### Workflow

```
Natural language description
    │
    ▼
Claude 3.5 Sonnet
    │
    ├── --format cfn       → CloudFormation YAML
    │                         write_iac_file() → validate_cloudformation()
    ├── --format terraform → main.tf + variables.tf + outputs.tf
    │                         write_iac_file() × 3
    └── --format cdk       → CDK app (Python)
                              write_iac_file()
```

### Run locally

```bash
cd iac-generator

python agent.py --format cfn \
  --description "VPC with 2 public and 2 private subnets, NAT Gateway" \
  --output infra/vpc.yaml

python agent.py --format terraform \
  --description "S3 bucket with versioning, encryption, CloudFront CDN" \
  --output infra/s3_cdn

python agent.py --format cdk \
  --description "Serverless API: Lambda, API Gateway, DynamoDB" \
  --output infra/api
```

### Invoke via AgentCore Runtime

```bash
RUNTIME_ARN=$(aws bedrock-agentcore list-agent-runtimes --region us-east-1 \
  --query 'agentRuntimes[?agentRuntimeName==`iac_generator_agent`].agentRuntimeArn' \
  --output text)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $RUNTIME_ARN \
  --runtime-session-id "session-$(date +%s)" \
  --payload '{"prompt": "Generate CloudFormation for ECS Fargate with ALB and auto-scaling. Save to output/ecs.yaml"}' \
  --region us-east-1
```

### Test

```bash
python test_iac_generator.py -v
# Ran 8 tests in 0.4s  OK
```

---

## Agent 3 — Observability / RCA Agent

### STAR Summary

| | |
|---|---|
| **Situation** | During incidents, engineers manually correlate CloudWatch alarms, logs, metrics, recent deployments, and config changes — a process that takes 30–90 minutes under pressure. |
| **Task** | Autonomously investigate an incident across all signal sources and produce a structured RCA report with remediation steps. |
| **Action** | Runs a 6-step investigation: active alarms → error logs → metric stats → recent deployments → CloudTrail config changes → correlation. Writes a timestamped RCA report with timeline, findings, root cause, and recommendations. |
| **Result** | Complete RCA report in under 2 minutes, covering signals that would take an engineer 30–60 minutes to gather manually. |

### Workflow

```
Incident description
    │
    ▼
get_cloudwatch_alarms()      ← what alarms are firing?
    ▼
get_recent_logs()            ← what errors appear in logs?
    ▼
get_metric_stats()           ← CPU / latency / error rate trend?
    ▼
get_recent_deployments()     ← any deploys in last 24h?
    ▼
get_cloudtrail_events()      ← any config changes on the resource?
    ▼
Claude 3.5 Sonnet            ← correlate → root cause
    ▼
write_rca_report()           → rca_report.md
    ├── Timeline
    ├── Findings
    ├── Root Cause
    └── Recommendations (immediate / short-term / long-term)
```

### Run locally

```bash
cd observability-rca

python agent.py \
  --incident "prod-api p99 latency jumped from 120ms to 8500ms at 10:00 UTC" \
  --log-group /aws/ecs/prod-api \
  --resource prod-aurora-cluster \
  --region us-east-1 \
  --output output/rca_high_latency.md
```

### Invoke via AgentCore Runtime

```bash
RUNTIME_ARN=$(aws bedrock-agentcore list-agent-runtimes --region us-east-1 \
  --query 'agentRuntimes[?agentRuntimeName==`observability_rca_agent`].agentRuntimeArn' \
  --output text)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $RUNTIME_ARN \
  --runtime-session-id "session-$(date +%s)" \
  --payload '{
    "prompt": "Investigate: prod-api p99 latency > 8s since 10:00 UTC. Log group: /aws/ecs/prod-api. Resource: prod-aurora-cluster. Write RCA to output/rca.md"
  }' \
  --region us-east-1
```

### Test

```bash
python test_rca_agent.py -v
# Ran 10 tests in 0.6s  OK
```

### Sample RCA Outputs

| File | Incident | Root Cause |
|------|----------|------------|
| `output/rca_high_latency.md` | p99 latency 120ms → 8500ms | RDS param change + unindexed query in deploy |
| `output/rca_lambda_errors.md` | Lambda error rate 15% | Memory 1024MB → 128MB, CPU throttled |
| `output/rca_rds_connections.md` | 503s, connection pool full | Traffic spike, no RDS Proxy |
| `output/rca_ecs_crash_loop.md` | Tasks OOMKilled | 780MB ML model, 256MB memory limit |
| `output/rca_deploy_regression.md` | 5xx after deploy | Missing `DISCOUNT_SERVICE_URL` env var |

---

## Run All Tests

```bash
python jenkins-migration-agent/test_migration.py -v
python iac-generator/test_iac_generator.py -v
python observability-rca/test_rca_agent.py -v
```

---

## Required IAM Permissions

The `event-agent-role` needs these additional permissions for the DevOps agents:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetMetricStatistics",
      "logs:FilterLogEvents",
      "codedeploy:ListApplications",
      "codedeploy:ListDeploymentGroups",
      "codedeploy:ListDeployments",
      "codedeploy:GetDeployment",
      "cloudtrail:LookupEvents"
    ],
    "Resource": "*"
  }]
}
```

---

## Integration with AIEOS

These agents are registered in the AIEOS platform at [Intelligent_Event_Agent_with_AgentCore](https://github.com/catchmeraman/Intelligent_Event_Agent_with_AgentCore).

From the AIEOS Streamlit UI, select the agent from the sidebar:
- **Jenkins Migration** — paste a Jenkinsfile, choose target platform
- **IaC Generator** — describe infrastructure in plain English
- **Observability/RCA** — describe an incident, get a full RCA report
