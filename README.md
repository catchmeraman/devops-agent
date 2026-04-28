# DevOps AI Agents

Three production-grade AI agents built with [Strands Agents](https://strandsagents.com) + AWS Bedrock (Claude 3.5 Sonnet) to automate the most time-consuming DevOps workflows.

---

## Agents at a Glance

| Agent | What it does | Input | Output |
|-------|-------------|-------|--------|
| **Jenkins Migration** | Converts Jenkinsfiles to ADO / GitLab CI | `Jenkinsfile` | `azure-pipelines.yml` or `.gitlab-ci.yml` |
| **IaC Generator** | Generates CFN / Terraform / CDK from plain English | Natural language description | `.yaml`, `.tf`, or `.py` |
| **Observability / RCA** | Investigates incidents, correlates signals, writes RCA | Incident description + log group | `rca_report.md` |

---

## Repository Structure

```
devops-agent/
├── requirements.txt
├── config/
│   ├── mcp_servers.json              # MCP config for Kiro / Claude / Cursor
│   ├── SETUP_DEVOPS_AGENT.md         # AWS DevOps Agent setup guide
│   └── SETUP_IAC_CICD.md             # IaC MCP + CodePipeline setup guide
│
├── jenkins-migration-agent/
│   ├── agent.py                      # Migration agent (Strands + Bedrock)
│   ├── test_migration.py             # Unit tests
│   └── sample/
│       ├── Jenkinsfile               # Sample input
│       └── .gitlab-ci.yml            # Sample output
│
├── iac-generator/
│   ├── agent.py                      # IaC generation agent
│   ├── test_iac_generator.py         # Unit tests
│   └── samples/
│       ├── 01_vpc_with_nat.yaml      # CFN: VPC + subnets + NAT GW
│       ├── 02_ecs_fargate_alb.yaml   # CFN: ECS Fargate + ALB + auto-scaling
│       ├── 03_rds_aurora/            # Terraform: Aurora PostgreSQL cluster
│       ├── 04_serverless_api_cdk.py  # CDK: Lambda + API GW + DynamoDB
│       ├── 05_codepipeline_ecs.yaml  # CFN: CodePipeline → GitHub → ECS
│       ├── 06_s3_cloudfront.tf       # Terraform: S3 + CloudFront CDN
│       └── 07_cloudwatch_alarms.yaml # CFN: Alarms for ECS/RDS/Lambda/ALB
│
└── observability-rca/
    ├── agent.py                      # RCA investigation agent
    ├── test_rca_agent.py             # Unit tests (mocked boto3)
    ├── samples/
    │   └── incidents.py              # 5 sample incident prompts
    └── output/
        ├── rca_high_latency.md       # Sample: DB query + deploy latency spike
        ├── rca_lambda_errors.md      # Sample: Lambda memory reduction → timeout
        ├── rca_rds_connections.md    # Sample: Connection pool exhausted
        ├── rca_ecs_crash_loop.md     # Sample: OOMKilled crash loop
        └── rca_deploy_regression.md  # Sample: Missing env var → 5xx after deploy
```

---

## Setup (One-time)

### Prerequisites

- Python 3.10+
- AWS account with Bedrock access (Claude 3.5 Sonnet enabled in `us-east-1`)
- AWS CLI configured (`aws configure`)

### Step 1 — Clone & install

```bash
git clone https://github.com/catchmeraman/devops-agent.git
cd devops-agent
pip install -r requirements.txt
```

### Step 2 — Enable Bedrock model access

```
AWS Console → Amazon Bedrock → Model access → Request access
→ Anthropic Claude 3.5 Sonnet → Save changes
```

### Step 3 — Set environment variables

```bash
export AWS_REGION=us-east-1
export AWS_PROFILE=default          # or your named profile
```

### Step 4 — Verify AWS credentials

```bash
aws sts get-caller-identity
aws bedrock list-foundation-models --region us-east-1 --query \
  "modelSummaries[?contains(modelId,'claude-3-5-sonnet')].[modelId]" --output table
```

---

## Agent 1 — Jenkins Migration Agent

### STAR Summary

| | |
|---|---|
| **Situation** | Teams migrating from Jenkins to Azure DevOps or GitLab CI spend days manually rewriting pipelines, often missing plugin equivalents or post-build hooks. |
| **Task** | Automatically parse any Jenkinsfile and produce a correct, runnable pipeline YAML for the target platform. |
| **Action** | The agent parses stages, steps, env vars, triggers, and post hooks via regex. It maps 10 common Jenkins plugins (Maven, Docker, SonarQube, Terraform, etc.) to native ADO tasks or GitLab script commands. Unknown plugins are flagged as gaps. |
| **Result** | A complete `azure-pipelines.yml` or `.gitlab-ci.yml` generated in seconds, with a gap report highlighting anything needing manual review. |

### Workflow

```
Jenkinsfile
    │
    ▼
parse_jenkinsfile()
    ├── stages / steps
    ├── env vars
    ├── triggers (cron)
    └── post hooks (always/success/failure)
    │
    ▼
explain_migration_gaps()          ← flags unknown plugins
    │
    ▼
migrate_jenkinsfile()
    ├── to_ado()    → azure-pipelines.yml
    └── to_gitlab() → .gitlab-ci.yml
```

### Deploy & Run

```bash
cd jenkins-migration-agent

# Migrate sample to GitLab CI
python agent.py --jenkinsfile sample/Jenkinsfile --target gitlab

# Migrate sample to Azure DevOps
python agent.py --jenkinsfile sample/Jenkinsfile --target ado

# Migrate your own Jenkinsfile
python agent.py --jenkinsfile /path/to/your/Jenkinsfile --target gitlab
```

### Test

```bash
python test_migration.py -v
```

Expected output:
```
test_ado_output_is_valid_yaml ... ok
test_gitlab_output_has_stages ... ok
test_plugin_mapping_docker    ... ok
test_gap_detection            ... ok
----------------------------------------------------------------------
Ran 4 tests in 0.3s  OK
```

---

## Agent 2 — IaC Generator Agent

### STAR Summary

| | |
|---|---|
| **Situation** | Writing CloudFormation, Terraform, or CDK from scratch is slow and error-prone — engineers spend hours on boilerplate, IAM roles, and resource wiring. |
| **Task** | Generate complete, production-ready IaC from a single natural language description. |
| **Action** | The agent uses Claude 3.5 Sonnet to generate IaC, then calls `write_iac_file()` to save it and `validate_cloudformation()` to structurally verify CFN templates before returning. |
| **Result** | A validated, deployable IaC file in seconds — CFN YAML, Terraform HCL (main + variables + outputs), or a full CDK app. |

### Workflow

```
Natural language description
    │
    ▼
Claude 3.5 Sonnet (reasoning)
    │
    ├── format=cfn       → generate CloudFormation YAML
    │                       write_iac_file() → validate_cloudformation()
    │
    ├── format=terraform → generate main.tf + variables.tf + outputs.tf
    │                       write_iac_file() × 3
    │
    └── format=cdk       → generate CDK app (Python or TypeScript)
                            write_iac_file()
```

### Deploy & Run

```bash
cd iac-generator

# Generate CloudFormation — VPC
python agent.py \
  --format cfn \
  --description "VPC with 2 public and 2 private subnets, NAT Gateway, and flow logs" \
  --output infra/vpc.yaml

# Generate Terraform — S3 + CloudFront
python agent.py \
  --format terraform \
  --description "S3 bucket with versioning, AES256 encryption, and CloudFront CDN" \
  --output infra/s3_cdn

# Generate CDK — Serverless API
python agent.py \
  --format cdk \
  --description "Serverless REST API: Lambda (Python 3.12), API Gateway, DynamoDB table" \
  --output infra/serverless_api

# Validate an existing CFN template
python -c "
from agent import validate_cloudformation
print(validate_cloudformation('samples/01_vpc_with_nat.yaml'))
"
```

### Test

```bash
python test_iac_generator.py -v
```

Expected output:
```
test_write_yaml_file              ... ok
test_write_terraform_file         ... ok
test_valid_vpc_template           ... ok
test_valid_lambda_template        ... ok
test_invalid_template_missing_resources ... ok
test_vpc_cfn_parses               ... ok
test_lambda_cfn_parses            ... ok
test_cdk_python_structure         ... ok
----------------------------------------------------------------------
Ran 8 tests in 0.4s  OK
```

---

## Agent 3 — Observability / RCA Agent

### STAR Summary

| | |
|---|---|
| **Situation** | During incidents, engineers manually correlate CloudWatch alarms, logs, metrics, recent deployments, and config changes — a process that takes 30–90 minutes under pressure. |
| **Task** | Autonomously investigate an incident across all signal sources and produce a structured Root Cause Analysis report with remediation steps. |
| **Action** | The agent runs a systematic 6-step investigation: active alarms → error logs → metric stats → recent deployments → CloudTrail config changes → correlation. It then writes a timestamped RCA report with timeline, findings, root cause, and recommendations. |
| **Result** | A complete RCA report in under 2 minutes, covering signals that would take an engineer 30–60 minutes to gather manually. |

### Workflow

```
Incident description
    │
    ▼
get_cloudwatch_alarms()       ← what alarms are firing?
    │
    ▼
get_recent_logs()             ← what errors appear in logs?
    │
    ▼
get_metric_stats()            ← CPU / latency / error rate trend?
    │
    ▼
get_recent_deployments()      ← any deploys in last 24h?
    │
    ▼
get_cloudtrail_events()       ← any config changes on the resource?
    │
    ▼
Claude 3.5 Sonnet             ← correlate all signals → root cause
    │
    ▼
write_rca_report()            → rca_report.md
    ├── Timeline
    ├── Findings (alarms / logs / metrics / deploys / CloudTrail)
    ├── Root Cause
    └── Recommendations (immediate / short-term / long-term)
```

### Deploy & Run

```bash
cd observability-rca

# Investigate high latency incident
python agent.py \
  --incident "prod-api p99 latency jumped from 120ms to 8500ms at 10:00 UTC" \
  --log-group /aws/ecs/prod-api \
  --resource prod-aurora-cluster \
  --region us-east-1 \
  --output output/rca_high_latency.md

# Investigate Lambda errors
python agent.py \
  --incident "Lambda items-api error rate 15% since 14:30 UTC" \
  --log-group /aws/lambda/items-api \
  --resource items-api \
  --output output/rca_lambda_errors.md

# Investigate ECS crash loop
python agent.py \
  --incident "ECS prod-api tasks crash-looping, RunningCount oscillates 0-1 since 08:00 UTC" \
  --log-group /aws/ecs/prod-api \
  --resource prod-cluster \
  --output output/rca_ecs_crash_loop.md

# Run all 5 sample incidents programmatically
python -c "
from samples.incidents import INCIDENTS
from agent import build_agent
agent = build_agent()
for key, inc in INCIDENTS.items():
    print(f'--- Investigating: {inc[\"title\"]} ---')
    agent(inc['prompt'])
"
```

### Test

```bash
python test_rca_agent.py -v
```

Expected output:
```
test_returns_active_alarms        ... ok
test_no_alarms_returns_message    ... ok
test_boto_error_handled           ... ok
test_returns_error_logs           ... ok
test_no_events_returns_message    ... ok
test_returns_datapoints           ... ok
test_returns_deployments          ... ok
test_returns_config_changes       ... ok
test_writes_report_file           ... ok
test_report_contains_all_sections ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.6s  OK
```

### Sample RCA Outputs

| File | Incident | Root Cause |
|------|----------|------------|
| `output/rca_high_latency.md` | p99 latency 120ms → 8500ms | RDS param change + unindexed query in new deploy |
| `output/rca_lambda_errors.md` | Lambda error rate 15% | Memory reduced 1024MB → 128MB, CPU throttled |
| `output/rca_rds_connections.md` | 503s, connection pool full | Marketing traffic spike, no RDS Proxy |
| `output/rca_ecs_crash_loop.md` | Tasks OOMKilled, crash loop | New image loads 780MB ML model, limit was 256MB |
| `output/rca_deploy_regression.md` | 5xx after deploy | Missing `DISCOUNT_SERVICE_URL` env var |

---

## Required IAM Permissions

Attach this inline policy to the IAM role / user running the agents:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
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
    }
  ]
}
```

---

## Run All Tests

```bash
# From repo root
python jenkins-migration-agent/test_migration.py -v
python iac-generator/test_iac_generator.py -v
python observability-rca/test_rca_agent.py -v
```
