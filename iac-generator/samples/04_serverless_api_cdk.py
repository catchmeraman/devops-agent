import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class ServerlessApiStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB table
        table = dynamodb.Table(
            self, "ItemsTable",
            table_name="items",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Lambda function
        fn = lambda_.Function(
            self, "ApiHandler",
            function_name="items-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import json, boto3, os
ddb = boto3.resource('dynamodb')
table = ddb.Table(os.environ['TABLE_NAME'])

def handler(event, context):
    method = event['httpMethod']
    if method == 'GET':
        result = table.scan()
        return {'statusCode': 200, 'body': json.dumps(result['Items'])}
    elif method == 'POST':
        item = json.loads(event['body'])
        table.put_item(Item=item)
        return {'statusCode': 201, 'body': json.dumps(item)}
    return {'statusCode': 405, 'body': 'Method not allowed'}
"""),
            environment={"TABLE_NAME": table.table_name},
            log_retention=logs.RetentionDays.ONE_MONTH,
            tracing=lambda_.Tracing.ACTIVE,
        )

        table.grant_read_write_data(fn)

        # API Gateway
        api = apigw.RestApi(
            self, "ItemsApi",
            rest_api_name="items-api",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                logging_level=apigw.MethodLoggingLevel.INFO,
                tracing_enabled=True,
            ),
        )

        items = api.root.add_resource("items")
        integration = apigw.LambdaIntegration(fn)
        items.add_method("GET", integration)
        items.add_method("POST", integration)

        cdk.CfnOutput(self, "ApiUrl", value=api.url)
        cdk.CfnOutput(self, "TableName", value=table.table_name)


app = cdk.App()
ServerlessApiStack(app, "ServerlessApiStack",
    env=cdk.Environment(region="us-east-1"))
app.synth()
