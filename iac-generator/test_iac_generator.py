"""
Tests for IaC Generator Agent
Run: python test_iac_generator.py
"""
import os
import sys
import yaml
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))
from agent import validate_cloudformation, write_iac_file, build_agent

# ── Sample IaC content ────────────────────────────────────────────────────────

SAMPLE_VPC_CFN = """
AWSTemplateFormatVersion: '2010-09-09'
Description: VPC with public and private subnets
Parameters:
  VpcCidr:
    Type: String
    Default: 10.0.0.0/16
Resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: !Ref VpcCidr
      EnableDnsSupport: true
      EnableDnsHostnames: true
      Tags:
        - Key: Name
          Value: prod-vpc
  PublicSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.1.0/24
      AvailabilityZone: !Select [0, !GetAZs '']
      MapPublicIpOnLaunch: true
  PrivateSubnet1:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref VPC
      CidrBlock: 10.0.10.0/24
      AvailabilityZone: !Select [0, !GetAZs '']
  InternetGateway:
    Type: AWS::EC2::InternetGateway
  VPCGatewayAttachment:
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      VpcId: !Ref VPC
      InternetGatewayId: !Ref InternetGateway
Outputs:
  VpcId:
    Value: !Ref VPC
    Export:
      Name: prod-vpc-id
"""

SAMPLE_LAMBDA_CFN = """
AWSTemplateFormatVersion: '2010-09-09'
Description: Lambda function with API Gateway
Resources:
  LambdaRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  MyFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: my-api-handler
      Runtime: python3.12
      Handler: index.handler
      Role: !GetAtt LambdaRole.Arn
      Code:
        ZipFile: |
          def handler(event, context):
              return {"statusCode": 200, "body": "Hello"}
      Environment:
        Variables:
          ENV: production
Outputs:
  FunctionArn:
    Value: !GetAtt MyFunction.Arn
"""

SAMPLE_TERRAFORM_MAIN = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_s3_bucket" "data" {
  bucket = var.bucket_name
  tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
"""

SAMPLE_TERRAFORM_VARS = """
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}
"""

SAMPLE_CDK_PYTHON = """
import aws_cdk as cdk
from aws_cdk import (
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ec2 as ec2,
)
from constructs import Construct

class FargateServiceStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "AppVpc", max_azs=2)

        cluster = ecs.Cluster(self, "AppCluster", vpc=vpc)

        ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "AppService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry("nginx:latest"),
                container_port=80,
            ),
            public_load_balancer=True,
        )

app = cdk.App()
FargateServiceStack(app, "FargateServiceStack", env=cdk.Environment(region="us-east-1"))
app.synth()
"""

# ── Unit tests ────────────────────────────────────────────────────────────────

class TestWriteIacFile(unittest.TestCase):
    def setUp(self):
        self.test_files = []

    def tearDown(self):
        for f in self.test_files:
            if os.path.exists(f):
                os.remove(f)

    def _track(self, path):
        self.test_files.append(path)
        return path

    def test_write_yaml_file(self):
        path = self._track("/tmp/test_cfn.yaml")
        result = write_iac_file(path, SAMPLE_VPC_CFN)
        self.assertIn("Written", result)
        self.assertTrue(os.path.exists(path))

    def test_write_terraform_file(self):
        path = self._track("/tmp/test_main.tf")
        result = write_iac_file(path, SAMPLE_TERRAFORM_MAIN)
        self.assertIn("Written", result)
        with open(path) as f:
            content = f.read()
        self.assertIn("aws_s3_bucket", content)

    def test_write_cdk_file(self):
        path = self._track("/tmp/test_cdk_app.py")
        result = write_iac_file(path, SAMPLE_CDK_PYTHON)
        self.assertIn("Written", result)


class TestValidateCloudFormation(unittest.TestCase):
    def setUp(self):
        self.test_files = []

    def tearDown(self):
        for f in self.test_files:
            if os.path.exists(f):
                os.remove(f)

    def _write(self, path, content):
        with open(path, "w") as f:
            f.write(content)
        self.test_files.append(path)
        return path

    def test_valid_vpc_template(self):
        path = self._write("/tmp/vpc.yaml", SAMPLE_VPC_CFN)
        result = validate_cloudformation(path)
        self.assertIn("VALID", result)
        self.assertIn("6", result)  # 6 resources

    def test_valid_lambda_template(self):
        path = self._write("/tmp/lambda.yaml", SAMPLE_LAMBDA_CFN)
        result = validate_cloudformation(path)
        self.assertIn("VALID", result)

    def test_invalid_template_missing_resources(self):
        bad = "AWSTemplateFormatVersion: '2010-09-09'\nDescription: Bad template\n"
        path = self._write("/tmp/bad.yaml", bad)
        result = validate_cloudformation(path)
        self.assertIn("INVALID", result)
        self.assertIn("Resources", result)

    def test_nonexistent_file(self):
        result = validate_cloudformation("/tmp/does_not_exist.yaml")
        self.assertIn("ERROR", result)


class TestSampleTemplateStructure(unittest.TestCase):
    """Validate sample templates parse correctly as YAML."""

    def test_vpc_cfn_parses(self):
        tpl = yaml.safe_load(SAMPLE_VPC_CFN)
        self.assertIn("Resources", tpl)
        self.assertIn("VPC", tpl["Resources"])
        self.assertIn("Outputs", tpl)

    def test_lambda_cfn_parses(self):
        tpl = yaml.safe_load(SAMPLE_LAMBDA_CFN)
        self.assertIn("MyFunction", tpl["Resources"])
        self.assertEqual(tpl["Resources"]["MyFunction"]["Type"], "AWS::Lambda::Function")

    def test_terraform_vars_structure(self):
        # Basic check: all variable blocks present
        for var in ["region", "bucket_name", "environment"]:
            self.assertIn(var, SAMPLE_TERRAFORM_VARS)

    def test_cdk_python_structure(self):
        self.assertIn("FargateServiceStack", SAMPLE_CDK_PYTHON)
        self.assertIn("ApplicationLoadBalancedFargateService", SAMPLE_CDK_PYTHON)


if __name__ == "__main__":
    unittest.main(verbosity=2)
