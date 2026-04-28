# DevOps AI Agents

## Architecture

```
Use Case                  Solution                          Status
─────────────────────────────────────────────────────────────────
IaC Generator             AWS IaC MCP + Terraform MCP       Config only
CI/CD Orchestrator        AWS MCP (CodePipeline SOPs)        Config only
Observability/RCA         AWS DevOps Agent + MCP connectors  Setup only
Jenkins → ADO/GitLab      jenkins-migration-agent/agent.py   Custom built
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up existing tools
- IaC + CI/CD: follow `config/SETUP_IAC_CICD.md`
- Observability: follow `config/SETUP_DEVOPS_AGENT.md`

### 3. Run Jenkins Migration Agent
```bash
cd jenkins-migration-agent

# Migrate to Azure DevOps
python agent.py --jenkinsfile sample/Jenkinsfile --target ado

# Migrate to GitLab CI
python agent.py --jenkinsfile sample/Jenkinsfile --target gitlab
```

Outputs: `azure-pipelines.yml` or `.gitlab-ci.yml` in current directory.

## Environment Variables
```bash
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

## Files
```
devops-agents/
├── requirements.txt
├── config/
│   ├── mcp_servers.json          # MCP server config for Kiro/Claude/Cursor
│   ├── SETUP_DEVOPS_AGENT.md     # AWS DevOps Agent setup (Observability)
│   └── SETUP_IAC_CICD.md         # IaC MCP + CodePipeline setup
└── jenkins-migration-agent/
    ├── agent.py                  # Custom Jenkins migration agent
    └── sample/
        └── Jenkinsfile           # Sample for testing
```
