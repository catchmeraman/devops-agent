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
    model = BedrockModel(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0")
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

if __name__ == "__main__":
    """
    Jenkins Migration Agent
    =======================
    Converts a Jenkinsfile into an equivalent Azure DevOps (azure-pipelines.yml)
    or GitLab CI (.gitlab-ci.yml) pipeline using a Strands + Bedrock agent.

    How it works:
      1. parse_jenkinsfile()  — regex-extracts stages, steps, env vars, triggers, post hooks
      2. explain_migration_gaps() tool — flags any Jenkins plugins with no known equivalent
      3. migrate_jenkinsfile() tool  — calls to_ado() or to_gitlab() and writes the output YAML

    Usage:
      python agent.py --jenkinsfile sample/Jenkinsfile --target gitlab
      python agent.py --jenkinsfile sample/Jenkinsfile --target ado

    Output:
      azure-pipelines.yml  (ADO)
      .gitlab-ci.yml       (GitLab)

    Supported plugin mappings: maven, gradle, docker, sonarqube, junit,
    artifactory, aws, terraform, ansible, slack.
    Unknown plugins are flagged as gaps requiring manual review.

    Requirements:
      export AWS_REGION=us-east-1
      pip install strands-agents boto3 pyyaml
    """
    parser = argparse.ArgumentParser(description="Jenkins Migration Agent")
    parser.add_argument("--jenkinsfile", required=True, help="Path to Jenkinsfile")
    parser.add_argument("--target", required=True, choices=["ado", "gitlab"], help="Target platform")
    args = parser.parse_args()

    agent = build_agent()
    response = agent(
        f"Migrate {args.jenkinsfile} to {args.target}. "
        f"First check for gaps, then generate the pipeline YAML."
    )
    print(response)
