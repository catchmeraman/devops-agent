FROM public.ecr.aws/docker/library/python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir strands-agents boto3 pyyaml aws-cdk-lib constructs bedrock-agentcore-starter-toolkit

COPY iac-generator/ ./iac-generator/

ENV AWS_REGION=us-east-1
ENV BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

EXPOSE 8080
HEALTHCHECK CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["python", "iac-generator/agent.py"]
