"""Standalone test — no strands/boto3 needed"""
import re, yaml

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
    "junit":        None,
    "artifactory":  "jfrog rt upload",
    "aws":          "aws $AWS_ARGS",
    "terraform":    "terraform apply -auto-approve",
    "ansible":      "ansible-playbook $PLAYBOOK",
    "slack":        None,
}

def parse_jenkinsfile(content):
    result = {"stages": [], "env": {}, "agent": "any", "triggers": [], "post": {}}
    agent_match = re.search(r"agent\s+(\w+|{[^}]+})", content)
    if agent_match:
        result["agent"] = agent_match.group(1).strip()
    for k, v in re.findall(r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]", content):
        result["env"][k] = v
    if "cron" in content:
        cron_val = re.search(r"cron\s*\(['\"]([^'\"]+)['\"]\)", content)
        if cron_val:
            result["triggers"].append({"type": "cron", "value": cron_val.group(1)})
    for stage_match in re.finditer(r"stage\s*\(['\"]([^'\"]+)['\"]\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", content, re.DOTALL):
        name = stage_match.group(1)
        body = stage_match.group(2)
        steps = re.findall(r"(?:sh|bat|echo|script)\s+['\"]([^'\"]+)['\"]", body)
        plugins = [p for p in PLUGIN_MAP_ADO if re.search(rf"\b{p}\b", body, re.IGNORECASE)]
        result["stages"].append({"name": name, "steps": steps, "plugins": plugins})
    for condition in ["always", "success", "failure"]:
        m = re.search(rf"{condition}\s*\{{([^}}]+)\}}", content, re.DOTALL)
        if m:
            result["post"][condition] = re.findall(r"(?:sh|echo)\s+['\"]([^'\"]+)['\"]", m.group(1))
    return result

def to_gitlab(parsed):
    pipeline = {}
    if parsed["env"]:
        pipeline["variables"] = parsed["env"]
    pipeline["stages"] = [s["name"] for s in parsed["stages"]]
    for stage in parsed["stages"]:
        script = []
        for plugin in stage["plugins"]:
            cmd = PLUGIN_MAP_GITLAB.get(plugin)
            if cmd:
                script.append(cmd)
        script.extend(stage["steps"])
        job = {"stage": stage["name"], "script": script or ["echo 'no steps'"]}
        if "junit" in stage["plugins"]:
            job["artifacts"] = {"reports": {"junit": ["**/TEST-*.xml"]}}
        pipeline[re.sub(r"\W+", "_", stage["name"])] = job
    if parsed["post"].get("failure"):
        pipeline["notify_failure"] = {
            "stage": ".post", "script": parsed["post"]["failure"], "when": "on_failure"
        }
    return yaml.dump(pipeline, default_flow_style=False, sort_keys=False)

content = open("sample/Jenkinsfile").read()
parsed = parse_jenkinsfile(content)
print("Parsed stages :", [s["name"] for s in parsed["stages"]])
print("Env vars      :", list(parsed["env"].keys()))
print("Triggers      :", parsed["triggers"])
print()
output = to_gitlab(parsed)
print(output)
with open(".gitlab-ci.yml", "w") as f:
    f.write(output)
print("✅  Written to .gitlab-ci.yml")
