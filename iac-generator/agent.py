"""
IaC Generator Agent
Generates CloudFormation / Terraform / CDK from natural language descriptions.
Uses Strands + Bedrock. No MCP required — pure code generation via LLM tools.
"""
import json
import re
import argparse
from strands import Agent, tool
from strands.models import BedrockModel

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def generate_cloudformation(description: str, output_file: str = "template.yaml") -> str:
    """
    Generate a CloudFormation YAML template from a natural language description.
    Args:
        description: What infrastructure to create
        output_file: Where to save the template
    Returns:
        Path to generated file and summary
    """
    # The agent (LLM) will fill in the actual template via its reasoning;
    # this tool writes whatever the agent produces to disk.
    return f"GENERATE_CFN:{description}:{output_file}"


@tool
def generate_terraform(description: str, output_dir: str = "terraform") -> str:
    """
    Generate Terraform HCL files (main.tf, variables.tf, outputs.tf) from a description.
    Args:
        description: What infrastructure to create
        output_dir: Directory to write .tf files
    Returns:
        Summary of generated files
    """
    return f"GENERATE_TF:{description}:{output_dir}"


@tool
def generate_cdk(description: str, language: str = "python", output_dir: str = "cdk_app") -> str:
    """
    Generate AWS CDK app from a description.
    Args:
        description: What infrastructure to create
        language: 'python' or 'typescript'
        output_dir: Directory to write CDK app
    Returns:
        Summary of generated files
    """
    return f"GENERATE_CDK:{description}:{language}:{output_dir}"


@tool
def write_iac_file(file_path: str, content: str) -> str:
    """
    Write IaC content to a file.
    Args:
        file_path: Destination path
        content: File content (YAML, HCL, Python, TypeScript)
    Returns:
        Confirmation message
    """
    import os
    os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
    with open(file_path, "w") as f:
        f.write(content)
    return f"Written: {file_path} ({len(content)} chars)"


@tool
def validate_cloudformation(template_path: str) -> str:
    """
    Validate a CloudFormation template using basic structural checks.
    Args:
        template_path: Path to the YAML/JSON template
    Returns:
        Validation result
    """
    import yaml
    try:
        with open(template_path) as f:
            tpl = yaml.safe_load(f)
        required = {"AWSTemplateFormatVersion", "Resources"}
        missing = required - set(tpl.keys())
        if missing:
            return f"INVALID: Missing required sections: {missing}"
        resource_count = len(tpl.get("Resources", {}))
        return f"VALID: {resource_count} resources defined in {template_path}"
    except Exception as e:
        return f"ERROR: {e}"


# ── Agent ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert AWS Infrastructure-as-Code engineer.
When given a description, generate complete, production-ready IaC.

Rules:
- CloudFormation: valid YAML with AWSTemplateFormatVersion, Description, Parameters (if needed), Resources, Outputs
- Terraform: separate main.tf (resources), variables.tf, outputs.tf
- CDK: complete app with stack class, proper constructs, cdk.json

Always use write_iac_file to save generated content, then validate_cloudformation for CFN templates.
Be specific about resource names, regions, and best practices (encryption, tags, least-privilege IAM).
"""

def build_agent():
    model = BedrockModel(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0")
    return Agent(
        model=model,
        tools=[generate_cloudformation, generate_terraform, generate_cdk,
               write_iac_file, validate_cloudformation],
        system_prompt=SYSTEM_PROMPT
    )


if __name__ == "__main__":
    """
    IaC Generator Agent
    ===================
    Generates production-ready Infrastructure-as-Code from a natural language description
    using a Strands + Bedrock agent backed by Claude 3.5 Sonnet.

    How it works:
      1. You describe the infrastructure in plain English (--description)
      2. The agent selects the right generator tool based on --format:
           cfn       → write_iac_file() saves CloudFormation YAML, then
                       validate_cloudformation() checks structure
           terraform → write_iac_file() saves main.tf + variables.tf + outputs.tf
           cdk       → write_iac_file() saves a complete CDK app (Python or TypeScript)
      3. Output is written to --output (file for cfn, directory for terraform/cdk)

    Usage:
      python agent.py --format cfn \
        --description "VPC with 2 public and 2 private subnets and NAT Gateway" \
        --output infra/vpc.yaml

      python agent.py --format terraform \
        --description "S3 bucket with versioning, encryption, and CloudFront CDN" \
        --output infra/s3_cdn

      python agent.py --format cdk \
        --description "Serverless API: Lambda + API Gateway + DynamoDB" \
        --output infra/serverless_api

    Sample templates (samples/):
      01_vpc_with_nat.yaml        CFN  — VPC, subnets, NAT GW
      02_ecs_fargate_alb.yaml     CFN  — ECS Fargate + ALB + auto-scaling
      03_rds_aurora/              TF   — Aurora PostgreSQL cluster
      04_serverless_api_cdk.py    CDK  — Lambda + API GW + DynamoDB
      05_codepipeline_ecs.yaml    CFN  — CodePipeline → GitHub → ECS
      06_s3_cloudfront.tf         TF   — S3 + CloudFront CDN
      07_cloudwatch_alarms.yaml   CFN  — Alarms for ECS/RDS/Lambda/ALB

    Requirements:
      export AWS_REGION=us-east-1
      pip install strands-agents boto3 pyyaml
    """
    parser = argparse.ArgumentParser(description="IaC Generator Agent")
    parser.add_argument("--description", required=True, help="What to generate")
    parser.add_argument("--format", choices=["cfn", "terraform", "cdk"], default="cfn")
    parser.add_argument("--output", default="output", help="Output file or directory")
    args = parser.parse_args()

    agent = build_agent()
    prompt = (
        f"Generate {args.format.upper()} IaC for: {args.description}\n"
        f"Save output to: {args.output}\n"
        f"After generating, validate the template if it's CloudFormation."
    )
    response = agent(prompt)
    print(response)
