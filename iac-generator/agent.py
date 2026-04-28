# built: 1777388120
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
    model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    return Agent(
        model=model,
        tools=[generate_cloudformation, generate_terraform, generate_cdk,
               write_iac_file, validate_cloudformation],
        system_prompt=SYSTEM_PROMPT
    )

def _run_cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--description", required=True)
    parser.add_argument("--format", choices=["cfn", "terraform", "cdk"], default="cfn")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()
    print(build_agent()(f"Generate {args.format.upper()} IaC for: {args.description}\nSave output to: {args.output}"))


# ── AgentCore Runtime entrypoint ──
import sys as _sys, traceback as _tb

try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp as _App
    import json as _json

    _app = _App()

    @_app.entrypoint
    def runtime_handler(payload, context):
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode()
        if isinstance(payload, str):
            payload = _json.loads(payload)
        prompt = payload.get("prompt", "")
        if not prompt:
            return "Error: Missing prompt field."
        return str(build_agent()(prompt))

    if __name__ == "__main__":
        _app.run()

except ImportError as _ie:
    if __name__ == "__main__":
        _run_cli()
except Exception as _ex:
    _tb.print_exc(file=_sys.stderr)
    _sys.exit(1)
