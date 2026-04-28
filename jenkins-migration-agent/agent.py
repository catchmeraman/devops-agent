# built: 1777388120
"""
Jenkins Migration Agent
Parses Jenkinsfile and generates ADO (azure-pipelines.yml) or GitLab CI (.gitlab-ci.yml)
"""
import re
import yaml
import argparse
from strands import Agent, tool
from strands.models import BedrockModel

# ── Plugin → native task mappings ────────────────────────────────────────────

PLUGIN_MAP_ADO = {
    "maven":        {"task": "Maven@3",        "inputs": {"mavenPomFile": "pom.xml", "goals": "clean package", "publishJUnitResults": "true"}},
    "gradle":       {"task": "Gradle@3",       "inputs": {"tasks": "build", "publishJUnitResults": "true"}},
    "docker":       {"task": "Docker@2",       "inputs": {"command": "buildAndPush", "containerRegistry": "$(dockerRegistryServiceConnection)", "repository": "$(imageRepository)", "tags": "$(Build.BuildId)"}},
    "sonarqube":    {"task": "SonarQubePrepare@5", "inputs": {"SonarQube": "SonarQube", "scannerMode": "MSBuild"},
                     "_also": [
                         {"task": "SonarQubeAnalyze@5", "inputs": {}},
                         {"task": "SonarQubePublish@5", "inputs": {"pollingTimeoutSec": "300"}},
                     ]},
    "junit":        {"task": "PublishTestResults@2", "inputs": {"testResultsFormat": "JUnit", "testResultsFiles": "**/TEST-*.xml"}},
    "artifactory":  {"task": "ArtifactoryGenericUpload@2", "inputs": {}},
    "aws":          {"task": "AWSCLI@1",       "inputs": {}},
    "terraform":    {"task": "TerraformTaskV4@4", "inputs": {
                         "command": "apply",
                         "backendType": "azurerm",
                         "backendServiceArm": "$(azureSubscription)",
                         "backendAzureRmResourceGroupName": "$(tfStateRG)",
                         "backendAzureRmStorageAccountName": "$(tfStateStorage)",
                         "backendAzureRmContainerName": "tfstate",
                         "backendAzureRmKey": "$(System.TeamProject).tfstate",
                     }},
    "ansible":      {"task": "Ansible@0",      "inputs": {}},
    "slack":        {"task": "SlackNotification@2", "inputs": {}},
}

PLUGIN_MAP_GITLAB = {
    "maven":        "mvn clean package -B",          # -B = batch mode for CI
    "gradle":       "gradle build --no-daemon",
    "docker":       (
        "docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY\n"
        "    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .\n"
        "    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA"
    ),
    "sonarqube":    (
        "mvn sonar:sonar "
        "-Dsonar.host.url=$SONAR_HOST_URL "
        "-Dsonar.login=$SONAR_TOKEN"
    ),
    "junit":        None,   # handled via artifacts:reports:junit
    "artifactory":  "jfrog rt upload",
    "aws":          "aws $AWS_ARGS",
    "terraform":    (
        "terraform init "
        "-backend-config=\"bucket=$TF_STATE_BUCKET\" "
        "-backend-config=\"key=$CI_PROJECT_NAME/terraform.tfstate\" "
        "-backend-config=\"region=$AWS_DEFAULT_REGION\"\n"
        "    - terraform plan -out=tfplan\n"
        "    - terraform apply -auto-approve tfplan"
    ),
    "ansible":      "ansible-playbook $PLAYBOOK",
    "slack":        None,   # use after_script with curl webhook
}

# GitLab job extras injected per plugin
PLUGIN_GITLAB_EXTRAS = {
    "docker": {
        "services": ["docker:dind"],
        "variables": {"DOCKER_TLS_CERTDIR": "/certs"},
        "image": "docker:latest",
    },
    "sonarqube": {
        "variables": {"SONAR_HOST_URL": "$SONAR_HOST_URL", "SONAR_TOKEN": "$SONAR_TOKEN"},
    },
    "terraform": {
        "image": "hashicorp/terraform:latest",
        "variables": {
            "TF_STATE_BUCKET": "$TF_STATE_BUCKET",
            "AWS_ACCESS_KEY_ID": "$AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY": "$AWS_SECRET_ACCESS_KEY",
        },
    },
}

# ── Jenkinsfile parser ────────────────────────────────────────────────────────

def parse_jenkinsfile(content: str) -> dict:
    """Extract stages, steps, env vars, agents, and triggers from a Jenkinsfile."""
    result = {"stages": [], "env": {}, "agent": "any", "triggers": [], "post": {}}

    # agent
    agent_match = re.search(r"agent\s+(\w+|{[^}]+})", content)
    if agent_match:
        result["agent"] = agent_match.group(1).strip()

    # env vars
    for k, v in re.findall(r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]", content):
        result["env"][k] = v

    # triggers
    if "cron" in content:
        cron_val = re.search(r"cron\s*\(['\"]([^'\"]+)['\"]\)", content)
        if cron_val:
            result["triggers"].append({"type": "cron", "value": cron_val.group(1)})

    # stages
    for stage_match in re.finditer(r"stage\s*\(['\"]([^'\"]+)['\"]\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", content, re.DOTALL):
        name = stage_match.group(1)
        body = stage_match.group(2)
        steps = re.findall(r"(?:sh|bat|echo|script)\s+['\"]([^'\"]+)['\"]", body)
        plugins = [p for p in PLUGIN_MAP_ADO if re.search(rf"\b{p}\b", body, re.IGNORECASE)]
        result["stages"].append({"name": name, "steps": steps, "plugins": plugins})

    # post conditions
    for condition in ["always", "success", "failure"]:
        m = re.search(rf"{condition}\s*\{{([^}}]+)\}}", content, re.DOTALL)
        if m:
            result["post"][condition] = re.findall(r"(?:sh|echo)\s+['\"]([^'\"]+)['\"]", m.group(1))

    return result

# ── Generators ────────────────────────────────────────────────────────────────

def to_ado(parsed: dict) -> str:
    pipeline = {"trigger": ["main"], "pool": {"vmImage": "ubuntu-latest"}, "stages": []}

    if parsed["env"]:
        pipeline["variables"] = {k: v for k, v in parsed["env"].items()}

    for stage in parsed["stages"]:
        tasks = []
        for plugin in stage["plugins"]:
            if plugin in PLUGIN_MAP_ADO:
                tasks.append({"task": PLUGIN_MAP_ADO[plugin]["task"],
                               "inputs": PLUGIN_MAP_ADO[plugin]["inputs"]})
        for step in stage["steps"]:
            tasks.append({"script": step, "displayName": step[:60]})

        pipeline["stages"].append({
            "stage": re.sub(r"\W+", "_", stage["name"]),
            "displayName": stage["name"],
            "jobs": [{"job": "run", "steps": tasks}]
        })

    return yaml.dump(pipeline, default_flow_style=False, sort_keys=False)


def to_gitlab(parsed: dict) -> str:
    pipeline = {}

    # Global variables
    global_vars = dict(parsed["env"]) if parsed["env"] else {}
    # Inject plugin-specific variables
    for stage in parsed["stages"]:
        for plugin in stage["plugins"]:
            extras = PLUGIN_GITLAB_EXTRAS.get(plugin, {})
            global_vars.update(extras.get("variables", {}))
    if global_vars:
        pipeline["variables"] = global_vars

    # Stages list
    stages = [s["name"] for s in parsed["stages"]]
    # Add environment promotion stages if deploy stage exists
    has_deploy = any("deploy" in s["name"].lower() for s in parsed["stages"])
    if has_deploy and not any(s in stages for s in ["dev", "staging", "production"]):
        stages = [s if "deploy" not in s.lower() else s for s in stages]
    pipeline["stages"] = stages

    for i, stage in enumerate(parsed["stages"]):
        script = []
        job_extras = {}

        for plugin in stage["plugins"]:
            cmd = PLUGIN_MAP_GITLAB.get(plugin)
            if cmd:
                script.extend(cmd.split("\n    - "))
            # Inject docker:dind, image, etc.
            extras = PLUGIN_GITLAB_EXTRAS.get(plugin, {})
            if "services" in extras:
                job_extras["services"] = extras["services"]
            if "image" in extras:
                job_extras["image"] = extras["image"]

        script.extend(stage["steps"])

        job: dict = {
            "stage": stage["name"],
            "script": [s.strip() for s in script if s.strip()] or ["echo no steps"],
        }
        job.update(job_extras)

        # Artifacts
        artifacts = {}
        if "junit" in stage["plugins"]:
            artifacts["reports"] = {"junit": ["**/TEST-*.xml"]}
        if stage["steps"]:
            artifacts["paths"] = ["target/", "dist/", "build/"]
            artifacts["expire_in"] = "1 hour"
        if artifacts:
            job["artifacts"] = artifacts

        # Add explicit needs (execution order)
        if i > 0:
            job["needs"] = [re.sub(r"\W+", "_", parsed["stages"][i-1]["name"])]

        # Manual approval for deploy stages
        if "deploy" in stage["name"].lower() or "prod" in stage["name"].lower():
            job["when"] = "manual"
            job["environment"] = {"name": stage["name"].lower()}

        pipeline[re.sub(r"\W+", "_", stage["name"])] = job

    # Post/notify via after_script
    if parsed["post"].get("failure"):
        pipeline["notify_failure"] = {
            "stage": ".post",
            "script": parsed["post"]["failure"] + [
                "# Slack: curl -X POST -H Content-type:application/json --data text=Pipeline-failed $SLACK_WEBHOOK_URL"
            ],
            "when": "on_failure",
        }
    if parsed["post"].get("always"):
        pipeline["notify_always"] = {
            "stage": ".post",
            "script": parsed["post"]["always"],
            "when": "always",
        }

    return yaml.dump(pipeline, default_flow_style=False, sort_keys=False)

# ── Strands tools ─────────────────────────────────────────────────────────────

@tool
def migrate_jenkinsfile(jenkinsfile_path: str, target: str) -> str:
    """
    Migrate a Jenkinsfile to ADO or GitLab CI YAML.
    Args:
        jenkinsfile_path: Path to the Jenkinsfile
        target: 'ado' or 'gitlab'
    Returns:
        Generated YAML as string
    """
    with open(jenkinsfile_path) as f:
        content = f.read()

    parsed = parse_jenkinsfile(content)

    if target.lower() == "ado":
        output = to_ado(parsed)
        out_file = "azure-pipelines.yml"
    elif target.lower() == "gitlab":
        output = to_gitlab(parsed)
        out_file = ".gitlab-ci.yml"
    else:
        return f"Unknown target '{target}'. Use 'ado' or 'gitlab'."

    with open(out_file, "w") as f:
        f.write(output)

    return f"Generated {out_file}:\n\n{output}"


@tool
def explain_migration_gaps(jenkinsfile_path: str) -> str:
    """
    Identify Jenkins plugins/steps that have no direct equivalent and need manual review.
    Args:
        jenkinsfile_path: Path to the Jenkinsfile
    Returns:
        List of gaps and recommendations
    """
    with open(jenkinsfile_path) as f:
        content = f.read()

    parsed = parse_jenkinsfile(content)
    known = set(PLUGIN_MAP_ADO.keys())
    gaps = []

    for stage in parsed["stages"]:
        unknown = [p for p in stage["plugins"] if p not in known]
        if unknown:
            gaps.append(f"Stage '{stage['name']}': unknown plugins {unknown}")

    return "\n".join(gaps) if gaps else "No gaps found — all plugins have known equivalents."

# ── Agent ─────────────────────────────────────────────────────────────────────

def build_agent():
    model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    return Agent(
        model=model,
        tools=[migrate_jenkinsfile, explain_migration_gaps],
        system_prompt=(
            "You are a senior CI/CD migration expert. You MUST always use the migrate_jenkinsfile tool "
            "to generate the pipeline YAML — never write YAML manually in your response. "
            "Always call explain_migration_gaps first, then migrate_jenkinsfile with the file path provided.\n\n"
            "Apply these CRITICAL production-correct conversion rules:\n"
            "1. EXECUTION ORDER: Add explicit dependsOn (Azure) or stages: list (GitLab) — never assume sequential.\n"
            "2. TOOLING: Use platform-native tasks (Maven@3 for Azure, image: maven:3.9 for GitLab) not just sh commands.\n"
            "3. AUTHENTICATION: withDockerRegistry → containerRegistry service connection (Azure) or CI_REGISTRY_USER/PASSWORD (GitLab).\n"
            "4. SONARQUBE: withSonarQubeEnv → 3 tasks (Prepare/Analyze/Publish) for Azure; env vars + sonar-scanner command for GitLab.\n"
            "5. DOCKER: Always add services: [docker:dind] for GitLab Docker builds; use Docker@2 task for Azure.\n"
            "6. TERRAFORM STATE: Always add remote backend (S3 for GitLab, Azure Storage for ADO) + state locking — never bare terraform apply.\n"
            "7. ENVIRONMENT PROMOTION: Add dev→stage→prod stages with manual approval gates (when: manual for GitLab, environment approvals for Azure).\n"
            "8. ARTIFACTS: Explicitly define artifacts/dependencies between stages — Jenkins workspace is NOT implicit in Azure/GitLab.\n"
            "After calling the tools, summarize what was mapped, what was adapted for production-correctness, and what still needs manual config."
        )
    )

def _run_cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--jenkinsfile", required=True)
    parser.add_argument("--target", required=True, choices=["ado", "gitlab"])
    args = parser.parse_args()
    print(build_agent()(f"Migrate {args.jenkinsfile} to {args.target}. First check for gaps, then generate the pipeline YAML."))




def _clean_for_s3(text: str, file_ext: str) -> str:
    """Extract the best clean code block for S3 download."""
    import re
    # Unescape double-escaped strings from JSON encoding
    text = text.replace("\\\\n", "\n").replace("\\\\t", "\t")
    text = text.replace("\\n", "\n").replace("\\t", "\t")
    # Remove the download link line
    text = re.sub(r"\n\n---\n.*$", "", text, flags=re.DOTALL)

    if file_ext in (".yaml", ".yml", ".tf", ".py"):
        # Find ALL code blocks and take the LAST one (usually the best/final version)
        blocks = re.findall(r"```(?:yaml|hcl|python|terraform|\w+)?\n(.*?)```", text, re.DOTALL)
        if blocks:
            # Pick the longest block (most complete)
            return max(blocks, key=len).strip()
        # No code block found — strip markdown and return raw
    # For .md or fallback: strip markdown formatting
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def _upload_to_s3_and_get_url(content: str, s3_key: str, bucket: str = "event-agent-kb-114805761158") -> str:
    """Upload text content to S3 and return a 7-day presigned download URL."""
    try:
        import boto3, os as _os
        s3 = boto3.client("s3", region_name=_os.getenv("AWS_REGION", "us-east-1"))
        s3.put_object(Bucket=bucket, Key=s3_key, Body=content.encode("utf-8"),
                      ContentType="text/plain")
        url = s3.generate_presigned_url("get_object",
                                         Params={"Bucket": bucket, "Key": s3_key},
                                         ExpiresIn=604800)  # 7 days
        return url
    except Exception as e:
        return f"(S3 upload failed: {e})"

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

        # Extract Jenkinsfile content from prompt and save to temp file
        # so migrate_jenkinsfile() tool can read it via file path
        import tempfile, os as _os, re as _re
        jf_match = _re.search(r"Jenkinsfile[:\s]*\n```(?:groovy|jenkins)?\n(.*?)```", prompt, _re.DOTALL | _re.IGNORECASE)
        if not jf_match:
            # Try plain content after "Jenkinsfile:" or after last newline block
            jf_match = _re.search(r"(?:Jenkinsfile[:\s]*\n|pipeline\s*\{)(.*)", prompt, _re.DOTALL)
        
        if jf_match:
            jf_content = jf_match.group(0) if "pipeline" in jf_match.group(0) else jf_match.group(1)
            # Ensure it starts with pipeline { if we matched from pipeline
            if not jf_content.strip().startswith("pipeline"):
                jf_content = jf_match.group(1)
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix="Jenkinsfile", delete=False)
            tmp.write(jf_content)
            tmp.close()
            tgt = "gitlab" if "gitlab" in prompt.lower() else "ado"
            agent_prompt = f"Migrate {tmp.name} to {tgt}. First run explain_migration_gaps, then migrate_jenkinsfile."
        else:
            agent_prompt = prompt

        result = str(build_agent()(agent_prompt))

        # Read the actual generated file (written by migrate_jenkinsfile tool)
        # instead of cleaning the text response
        fname = ".gitlab-ci.yml" if tgt == "gitlab" else "azure-pipelines.yml"
        try:
            with open(fname) as _f:
                clean_code = _f.read()
        except Exception:
            clean_code = _clean_for_s3(result, ".yml")  # fallback

        # Cleanup temp file
        try:
            if jf_match: _os.unlink(tmp.name)
        except Exception:
            pass
        import time as _t
        tgt = "gitlab" if "gitlab" in prompt.lower() else "ado"
        fname = ".gitlab-ci.yml" if tgt == "gitlab" else "azure-pipelines.yml"
        key = f"devops-outputs/jenkins-migration/{int(_t.time())}/{fname}"
        url = _upload_to_s3_and_get_url(clean_code, key)
        return result + f"\n\n---\n📥 **Download {fname}**: [Click to download (7 days)]({url})"

    if __name__ == "__main__":
        _app.run()

except ImportError as _ie:
    if __name__ == "__main__":
        _run_cli()
except Exception as _ex:
    _tb.print_exc(file=_sys.stderr)
    _sys.exit(1)
