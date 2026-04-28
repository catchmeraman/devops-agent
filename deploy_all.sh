#!/bin/bash
# deploy_all.sh — Build, push, and deploy all 3 DevOps agents to AgentCore
# Usage: bash deploy_all.sh [jenkins|iac|rca|all]
set -e

ACCOUNT=114805761158
REGION=us-east-1
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/event-agent-role"
TARGET=${1:-all}

ECR_BASE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# Login to ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ECR_BASE

deploy_agent() {
  local NAME=$1       # e.g. jenkins_migration_agent
  local DOCKERFILE=$2 # e.g. jenkins-migration-agent/Dockerfile
  local ECR_REPO="${ECR_BASE}/bedrock-agentcore-${NAME}"

  echo ""
  echo "━━━ Deploying: $NAME ━━━"

  # Create ECR repo if missing
  aws ecr describe-repositories --repository-names "bedrock-agentcore-${NAME}" \
    --region $REGION &>/dev/null || \
  aws ecr create-repository --repository-name "bedrock-agentcore-${NAME}" \
    --region $REGION --image-scanning-configuration scanOnPush=true

  # Build & push
  docker build --platform linux/arm64 -f $DOCKERFILE -t "${ECR_REPO}:latest" .
  docker push "${ECR_REPO}:latest"

  # Deploy via AgentCore toolkit
  agentcore deploy --agent $NAME --region $REGION

  echo "✓ $NAME deployed"
}

case $TARGET in
  jenkins|all)
    deploy_agent "jenkins_migration_agent" "jenkins-migration-agent/Dockerfile"
    ;;&
  iac|all)
    deploy_agent "iac_generator_agent" "iac-generator/Dockerfile"
    ;;&
  rca|all)
    deploy_agent "observability_rca_agent" "observability-rca/Dockerfile"
    ;;
esac

echo ""
echo "━━━ All agents deployed. Verify: ━━━"
aws bedrock-agentcore list-agent-runtimes --region $REGION \
  --query 'agentRuntimes[*].[agentRuntimeName,status]' --output table
