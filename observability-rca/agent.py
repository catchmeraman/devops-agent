# built: 1777388120
"""
Observability / RCA Agent
Investigates incidents by correlating CloudWatch logs, metrics, alarms, and recent deployments.
Uses Strands + Bedrock + AWS MCP tools (CloudWatch MCP, CloudTrail MCP).
"""
import json
import argparse
from datetime import datetime, timedelta, timezone
from strands import Agent, tool
from strands.models import BedrockModel
import boto3

# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_cloudwatch_alarms(region: str = "us-east-1", state: str = "ALARM") -> str:
    """
    List CloudWatch alarms currently in a given state.
    Args:
        region: AWS region
        state: 'ALARM', 'OK', or 'INSUFFICIENT_DATA'
    Returns:
        JSON list of alarms
    """
    try:
        cw = boto3.client("cloudwatch", region_name=region)
        resp = cw.describe_alarms(StateValue=state)
        alarms = [
            {
                "name": a["AlarmName"],
                "metric": a.get("MetricName", "composite"),
                "namespace": a.get("Namespace", ""),
                "state_reason": a["StateReason"],
                "updated": a["StateUpdatedTimestamp"].isoformat(),
            }
            for a in resp["MetricAlarms"] + resp.get("CompositeAlarms", [])
        ]
        return json.dumps(alarms, indent=2) if alarms else "No alarms in state: " + state
    except Exception as e:
        return f"ERROR: {e}"


@tool
def get_recent_logs(log_group: str, minutes: int = 30, filter_pattern: str = "ERROR",
                    region: str = "us-east-1") -> str:
    """
    Fetch recent log events from a CloudWatch log group.
    Args:
        log_group: CloudWatch log group name
        minutes: How far back to look
        filter_pattern: CloudWatch filter pattern (e.g. 'ERROR', 'Exception')
        region: AWS region
    Returns:
        Matching log lines (up to 50)
    """
    try:
        logs = boto3.client("logs", region_name=region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        resp = logs.filter_log_events(
            logGroupName=log_group,
            startTime=int(start.timestamp() * 1000),
            endTime=int(end.timestamp() * 1000),
            filterPattern=filter_pattern,
            limit=50,
        )
        events = [e["message"] for e in resp.get("events", [])]
        return "\n".join(events) if events else f"No '{filter_pattern}' events in last {minutes}m"
    except Exception as e:
        return f"ERROR: {e}"


@tool
def get_metric_stats(namespace: str, metric_name: str, dimensions: str,
                     minutes: int = 60, region: str = "us-east-1") -> str:
    """
    Get CloudWatch metric statistics.
    Args:
        namespace: e.g. 'AWS/EC2', 'AWS/Lambda', 'AWS/RDS'
        metric_name: e.g. 'CPUUtilization', 'Errors', 'Latency'
        dimensions: JSON string, e.g. '[{"Name":"InstanceId","Value":"i-123"}]'
        minutes: Lookback window
        region: AWS region
    Returns:
        Datapoints as JSON
    """
    try:
        cw = boto3.client("cloudwatch", region_name=region)
        dims = json.loads(dimensions)
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dims,
            StartTime=start,
            EndTime=end,
            Period=300,
            Statistics=["Average", "Maximum", "Sum"],
        )
        points = sorted(resp["Datapoints"], key=lambda x: x["Timestamp"])
        return json.dumps([
            {"time": p["Timestamp"].isoformat(), "avg": p.get("Average"),
             "max": p.get("Maximum"), "sum": p.get("Sum")}
            for p in points
        ], indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@tool
def get_recent_deployments(region: str = "us-east-1", hours: int = 24) -> str:
    """
    List recent CodeDeploy deployments to correlate with incidents.
    Args:
        region: AWS region
        hours: How far back to look
    Returns:
        JSON list of recent deployments
    """
    try:
        cd = boto3.client("codedeploy", region_name=region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        apps = cd.list_applications().get("applications", [])
        deployments = []
        for app in apps[:5]:  # limit to avoid throttling
            dg = cd.list_deployment_groups(applicationName=app).get("deploymentGroups", [])
            for group in dg[:3]:
                resp = cd.list_deployments(
                    applicationName=app,
                    deploymentGroupName=group,
                    createTimeRange={"start": start, "end": end},
                )
                for dep_id in resp.get("deployments", [])[:5]:
                    info = cd.get_deployment(deploymentId=dep_id)["deploymentInfo"]
                    deployments.append({
                        "id": dep_id,
                        "app": app,
                        "group": group,
                        "status": info["status"],
                        "created": info["createTime"].isoformat(),
                    })
        return json.dumps(deployments, indent=2) if deployments else "No deployments found"
    except Exception as e:
        return f"ERROR (CodeDeploy): {e}"


@tool
def get_cloudtrail_events(resource_name: str, hours: int = 2,
                          region: str = "us-east-1") -> str:
    """
    Look up recent CloudTrail events for a resource (config changes, API calls).
    Args:
        resource_name: Resource name or ID to search
        hours: Lookback window
        region: AWS region
    Returns:
        Recent API events as JSON
    """
    try:
        ct = boto3.client("cloudtrail", region_name=region)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        resp = ct.lookup_events(
            LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": resource_name}],
            StartTime=start,
            EndTime=end,
            MaxResults=20,
        )
        events = [
            {
                "time": e["EventTime"].isoformat(),
                "event": e["EventName"],
                "user": e.get("Username", "unknown"),
                "source": e.get("EventSource", ""),
            }
            for e in resp.get("Events", [])
        ]
        return json.dumps(events, indent=2) if events else "No CloudTrail events found"
    except Exception as e:
        return f"ERROR (CloudTrail): {e}"


@tool
def write_rca_report(incident: str, findings: str, root_cause: str,
                     recommendations: str, output_file: str = "rca_report.md") -> str:
    """
    Write a structured Root Cause Analysis report to a markdown file.
    Args:
        incident: Incident description
        findings: What was found during investigation
        root_cause: Identified root cause
        recommendations: Remediation steps
        output_file: Output file path
    Returns:
        Confirmation
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"""# Root Cause Analysis Report
**Date:** {now}
**Incident:** {incident}

## Findings
{findings}

## Root Cause
{root_cause}

## Recommendations
{recommendations}
"""
    with open(output_file, "w") as f:
        f.write(content)
    return f"RCA report written to {output_file}"


# ── Agent ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer performing incident investigation.

When given an incident description:
1. Check active CloudWatch alarms
2. Pull recent error logs from relevant log groups
3. Check metric stats for the affected service
4. Look for recent deployments that may have caused the issue
5. Check CloudTrail for recent config changes
6. Correlate all findings to identify root cause
7. Write a structured RCA report with remediation steps

Be systematic. Always check multiple signals before concluding root cause.
Prioritize: recent deployments > config changes > resource exhaustion > external dependencies.
"""

def build_agent():
    model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    return Agent(
        model=model,
        tools=[get_cloudwatch_alarms, get_recent_logs, get_metric_stats,
               get_recent_deployments, get_cloudtrail_events, write_rca_report],
        system_prompt=SYSTEM_PROMPT
    )

def _run_cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", required=True)
    parser.add_argument("--log-group", default="")
    parser.add_argument("--resource", default="")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--output", default="rca_report.md")
    args = parser.parse_args()
    prompt = (f"Investigate: {args.incident}\n"
              + (f"Log group: {args.log_group}\n" if args.log_group else "")
              + (f"Resource: {args.resource}\n" if args.resource else "")
              + f"Region: {args.region}\nWrite RCA to: {args.output}")
    print(build_agent()(prompt))


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
