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
    "maven":        {"task": "Maven@3",        "inputs": {"goals": "$(goals)"}},
    "gradle":       {"task": "Gradle@3",       "inputs": {"tasks": "build"}},
    "docker":       {"task": "Docker@2",       "inputs": {"command": "buildAndPush"}},
    "sonarqube":    {"task": "SonarQubePrepare@5", "inputs": {}},
    "junit":        {"task": "PublishTestResults@2", "inputs": {"testResultsFormat": "JUnit"}},
    "artifactory":  {"task": "ArtifactoryGenericUpload@2", "inputs": {}},
    "aws":          {"task": "AWSCLI@1",       "inputs": {}},
    "terraform":    {"task": "TerraformTaskV4@4", "inputs": {"command": "apply"}},
    "ansible":      {"task": "Ansible@0",      "inputs": {}},
    "slack":        {"task": "SlackNotification@2", "inputs": {}},
}

PLUGIN_MAP_GITLAB = {
    "maven":        "mvn $GOALS",
    "gradle":       "gradle build",
    "docker":       "docker build -t $IMAGE . && docker push $IMAGE",
    "sonarqube":    "sonar-scanner",
    "junit":        None,   # handled via artifacts:reports
    "artifactory":  "jfrog rt upload",
    "aws":          "aws $AWS_ARGS",
    "terraform":    "terraform apply -auto-approve",
    "ansible":      "ansible-playbook $PLAYBOOK",
    "slack":        None,   # handled via notify keyword
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

    if parsed["env"]:
        pipeline["variables"] = parsed["env"]

    stages = [s["name"] for s in parsed["stages"]]
    pipeline["stages"] = stages

    for stage in parsed["stages"]:
        script = []
        for plugin in stage["plugins"]:
            cmd = PLUGIN_MAP_GITLAB.get(plugin)
            if cmd:
                script.append(cmd)
        script.extend(stage["steps"])

        job: dict = {"stage": stage["name"], "script": script or ["echo 'no steps'"]}

        if stage["plugins"] and "junit" in stage["plugins"]:
            job["artifacts"] = {"reports": {"junit": ["**/TEST-*.xml"]}}

        pipeline[re.sub(r"\W+", "_", stage["name"])] = job

    # post/notify
    if parsed["post"].get("failure"):
        pipeline["notify_failure"] = {
            "stage": ".post",
            "script": parsed["post"]["failure"],
            "when": "on_failure"
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
            "You are a CI/CD migration expert. Help users migrate Jenkins pipelines "
            "to Azure DevOps or GitLab CI. Use migrate_jenkinsfile to generate YAML "
            "and explain_migration_gaps to flag items needing manual review. "
            "Always explain what was mapped and what needs attention."
        )
    )

def _run_cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--jenkinsfile", required=True)
    parser.add_argument("--target", required=True, choices=["ado", "gitlab"])
    args = parser.parse_args()
    print(build_agent()(f"Migrate {args.jenkinsfile} to {args.target}. First check for gaps, then generate the pipeline YAML."))


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
