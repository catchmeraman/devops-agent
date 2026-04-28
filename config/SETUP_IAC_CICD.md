# IaC Generator + CI/CD Orchestrator Setup
# Uses: AWS IaC MCP + Terraform MCP + AWS API MCP (CodePipeline SOPs)

## What It Covers
- Generate CloudFormation / CDK / Terraform from natural language
- Validate and deploy IaC templates
- Set up CodePipeline CI/CD pipelines via AWS MCP SOPs

## 1. Install MCP Servers

```bash
# AWS IaC MCP (CDK + CloudFormation)
uvx awslabs.aws-iac-mcp-server@latest

# Terraform MCP (HashiCorp official)
npx -y @hashicorp/terraform-mcp-server

# AWS API MCP (CodePipeline, CodeBuild, etc.)
uvx awslabs.aws-api-mcp-server@latest
```

## 2. Configure in Kiro / Claude / Cursor

Add to your MCP config (`.kiro/settings/mcp.json` or equivalent):

```json
{
  "mcpServers": {
    "aws-iac": {
      "command": "uvx",
      "args": ["awslabs.aws-iac-mcp-server@latest"],
      "env": { "AWS_REGION": "us-east-1" }
    },
    "terraform": {
      "command": "npx",
      "args": ["-y", "@hashicorp/terraform-mcp-server"]
    },
    "aws-api": {
      "command": "uvx",
      "args": ["awslabs.aws-api-mcp-server@latest"],
      "env": { "AWS_REGION": "us-east-1" }
    }
  }
}
```

## 3. IaC Generation — Example Prompts

Once MCPs are connected, use natural language:

```
"Generate a CloudFormation template for a VPC with 2 public and 2 private subnets"

"Create a CDK stack for an ECS Fargate service with ALB and auto-scaling"

"Write Terraform for an RDS Aurora cluster with read replicas in us-east-1"

"Validate my template at ./infra/template.yaml and fix any issues"
```

## 4. CI/CD Pipeline Setup via AWS MCP SOP

The AWS MCP Server has a built-in SOP for CodePipeline:

```
"Set up a CodePipeline that builds from GitHub, runs tests in CodeBuild,
 and deploys to ECS on merge to main"
```

The SOP handles:
- Source stage (GitHub/CodeCommit/S3)
- Build stage (CodeBuild with buildspec)
- Test stage
- Deploy stage (ECS/Lambda/EC2/Beanstalk)
- Notifications (SNS/Slack)

## 5. Hybrid Pipeline Orchestration

For pipelines spanning AWS + Azure + on-prem, use Terraform MCP:

```
"Create Terraform to provision:
 - AWS CodePipeline for build/test
 - Azure DevOps release pipeline for staging deploy
 - Ansible playbook trigger for on-prem deploy"
```

## References
- [AWS IaC MCP](https://awslabs.github.io/mcp/servers/aws-iac-mcp-server)
- [Terraform MCP](https://github.com/hashicorp/terraform-mcp-server)
- [CodePipeline SOP](https://docs.aws.amazon.com/aws-mcp/latest/userguide/agent-sops-deployment-pipeline.html)
