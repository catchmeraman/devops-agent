"""
Tests for Observability / RCA Agent
Run: python test_rca_agent.py
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from agent import (
    get_cloudwatch_alarms, get_recent_logs, get_metric_stats,
    get_recent_deployments, get_cloudtrail_events, write_rca_report
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

MOCK_ALARMS = {
    "MetricAlarms": [
        {
            "AlarmName": "prod-api-high-latency",
            "MetricName": "Latency",
            "Namespace": "AWS/ApplicationELB",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 1 datapoint > 2000ms",
            "StateUpdatedTimestamp": datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
        },
        {
            "AlarmName": "prod-rds-cpu-high",
            "MetricName": "CPUUtilization",
            "Namespace": "AWS/RDS",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: CPU > 90%",
            "StateUpdatedTimestamp": datetime(2026, 4, 28, 10, 5, tzinfo=timezone.utc),
        },
    ],
    "CompositeAlarms": [],
}

MOCK_LOG_EVENTS = {
    "events": [
        {"message": "ERROR: Connection pool exhausted after 30s timeout", "timestamp": 1714298400000},
        {"message": "ERROR: Query timeout on orders table - missing index", "timestamp": 1714298460000},
        {"message": "WARN: Retry attempt 3/3 for DB connection", "timestamp": 1714298520000},
        {"message": "ERROR: 500 Internal Server Error - /api/v1/orders", "timestamp": 1714298580000},
    ]
}

MOCK_METRIC_STATS = {
    "Datapoints": [
        {"Timestamp": datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc), "Average": 120.0, "Maximum": 180.0, "Sum": 7200.0},
        {"Timestamp": datetime(2026, 4, 28, 9, 5, tzinfo=timezone.utc), "Average": 850.0, "Maximum": 2100.0, "Sum": 51000.0},
        {"Timestamp": datetime(2026, 4, 28, 9, 10, tzinfo=timezone.utc), "Average": 3200.0, "Maximum": 8500.0, "Sum": 192000.0},
    ]
}

MOCK_DEPLOYMENTS = {
    "applications": ["prod-api"],
}

MOCK_DEPLOYMENT_GROUPS = {"deploymentGroups": ["prod-api-group"]}

MOCK_DEPLOYMENT_LIST = {"deployments": ["d-ABC123XYZ"]}

MOCK_DEPLOYMENT_INFO = {
    "deploymentInfo": {
        "status": "Succeeded",
        "createTime": datetime(2026, 4, 28, 8, 45, tzinfo=timezone.utc),
    }
}

MOCK_CLOUDTRAIL_EVENTS = {
    "Events": [
        {
            "EventTime": datetime(2026, 4, 28, 8, 40, tzinfo=timezone.utc),
            "EventName": "ModifyDBParameterGroup",
            "Username": "ops-engineer",
            "EventSource": "rds.amazonaws.com",
        },
        {
            "EventTime": datetime(2026, 4, 28, 8, 30, tzinfo=timezone.utc),
            "EventName": "UpdateFunctionConfiguration",
            "Username": "ci-deploy-role",
            "EventSource": "lambda.amazonaws.com",
        },
    ]
}

# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGetCloudWatchAlarms(unittest.TestCase):
    @patch("boto3.client")
    def test_returns_active_alarms(self, mock_boto):
        mock_boto.return_value.describe_alarms.return_value = MOCK_ALARMS
        result = get_cloudwatch_alarms(region="us-east-1", state="ALARM")
        alarms = json.loads(result)
        self.assertEqual(len(alarms), 2)
        self.assertEqual(alarms[0]["name"], "prod-api-high-latency")
        self.assertIn("Latency", alarms[0]["metric"])

    @patch("boto3.client")
    def test_no_alarms_returns_message(self, mock_boto):
        mock_boto.return_value.describe_alarms.return_value = {
            "MetricAlarms": [], "CompositeAlarms": []
        }
        result = get_cloudwatch_alarms()
        self.assertIn("No alarms", result)

    @patch("boto3.client")
    def test_boto_error_handled(self, mock_boto):
        mock_boto.return_value.describe_alarms.side_effect = Exception("AccessDenied")
        result = get_cloudwatch_alarms()
        self.assertIn("ERROR", result)


class TestGetRecentLogs(unittest.TestCase):
    @patch("boto3.client")
    def test_returns_error_logs(self, mock_boto):
        mock_boto.return_value.filter_log_events.return_value = MOCK_LOG_EVENTS
        result = get_recent_logs("/aws/lambda/prod-api", minutes=30, filter_pattern="ERROR")
        self.assertIn("Connection pool exhausted", result)
        self.assertIn("missing index", result)

    @patch("boto3.client")
    def test_no_events_returns_message(self, mock_boto):
        mock_boto.return_value.filter_log_events.return_value = {"events": []}
        result = get_recent_logs("/aws/lambda/prod-api")
        self.assertIn("No", result)

    @patch("boto3.client")
    def test_log_group_not_found(self, mock_boto):
        mock_boto.return_value.filter_log_events.side_effect = Exception("ResourceNotFoundException")
        result = get_recent_logs("/aws/lambda/nonexistent")
        self.assertIn("ERROR", result)


class TestGetMetricStats(unittest.TestCase):
    @patch("boto3.client")
    def test_returns_datapoints(self, mock_boto):
        mock_boto.return_value.get_metric_statistics.return_value = MOCK_METRIC_STATS
        dims = json.dumps([{"Name": "LoadBalancer", "Value": "app/prod-alb/abc123"}])
        result = get_metric_stats("AWS/ApplicationELB", "TargetResponseTime", dims, minutes=60)
        points = json.loads(result)
        self.assertEqual(len(points), 3)
        # Verify spike is visible
        self.assertGreater(points[2]["avg"], points[0]["avg"])

    @patch("boto3.client")
    def test_invalid_dimensions_json(self, mock_boto):
        result = get_metric_stats("AWS/EC2", "CPUUtilization", "not-valid-json")
        self.assertIn("ERROR", result)


class TestGetRecentDeployments(unittest.TestCase):
    @patch("boto3.client")
    def test_returns_deployments(self, mock_boto):
        client = MagicMock()
        mock_boto.return_value = client
        client.list_applications.return_value = MOCK_DEPLOYMENTS
        client.list_deployment_groups.return_value = MOCK_DEPLOYMENT_GROUPS
        client.list_deployments.return_value = MOCK_DEPLOYMENT_LIST
        client.get_deployment.return_value = MOCK_DEPLOYMENT_INFO

        result = get_recent_deployments(region="us-east-1", hours=24)
        deps = json.loads(result)
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["id"], "d-ABC123XYZ")
        self.assertEqual(deps[0]["status"], "Succeeded")

    @patch("boto3.client")
    def test_no_apps_returns_message(self, mock_boto):
        mock_boto.return_value.list_applications.return_value = {"applications": []}
        result = get_recent_deployments()
        self.assertIn("No deployments", result)


class TestGetCloudTrailEvents(unittest.TestCase):
    @patch("boto3.client")
    def test_returns_config_changes(self, mock_boto):
        mock_boto.return_value.lookup_events.return_value = MOCK_CLOUDTRAIL_EVENTS
        result = get_cloudtrail_events("prod-rds-cluster", hours=2)
        events = json.loads(result)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "ModifyDBParameterGroup")
        self.assertEqual(events[0]["user"], "ops-engineer")

    @patch("boto3.client")
    def test_no_events_returns_message(self, mock_boto):
        mock_boto.return_value.lookup_events.return_value = {"Events": []}
        result = get_cloudtrail_events("some-resource")
        self.assertIn("No CloudTrail events", result)


class TestWriteRcaReport(unittest.TestCase):
    def setUp(self):
        self.report_path = "/tmp/test_rca_report.md"

    def tearDown(self):
        if os.path.exists(self.report_path):
            os.remove(self.report_path)

    def test_writes_report_file(self):
        result = write_rca_report(
            incident="High latency on prod-api (p99 > 8s)",
            findings="- ALB latency alarm fired at 10:00 UTC\n- DB CPU at 95%\n- Deploy d-ABC123 at 08:45 UTC",
            root_cause="RDS parameter group change at 08:40 UTC disabled query cache, "
                       "combined with deploy adding unindexed query on orders table",
            recommendations="1. Revert RDS parameter group\n2. Add index: CREATE INDEX ON orders(user_id)\n3. Rollback deploy d-ABC123",
            output_file=self.report_path,
        )
        self.assertIn("rca_report", result)
        self.assertTrue(os.path.exists(self.report_path))

        with open(self.report_path) as f:
            content = f.read()
        self.assertIn("Root Cause Analysis", content)
        self.assertIn("High latency", content)
        self.assertIn("Recommendations", content)

    def test_report_contains_all_sections(self):
        write_rca_report(
            incident="Lambda cold starts",
            findings="Cold start p99 = 12s",
            root_cause="Memory set to 128MB",
            recommendations="Increase memory to 1024MB",
            output_file=self.report_path,
        )
        with open(self.report_path) as f:
            content = f.read()
        for section in ["Findings", "Root Cause", "Recommendations"]:
            self.assertIn(section, content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
