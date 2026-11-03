import ujson as json
import os

import moto
import pytest
from boto3 import client, resource
from moto.ec2 import utils as ec2_utils

from cloud_functions.aws import generic

subnet_id = None


@pytest.fixture(autouse=True, scope="session")
def setup():
    global subnet_id
    aws = moto.mock_aws()
    aws.start()
    ecs = client("ecs", region_name="us-east-1")
    ecs.create_cluster(
        clusterName="UploadEventCluster",
        tags=[
            {"key": "Cost", "value": "AI"},
        ],
        capacityProviders=[
            "FARGATE",
        ],
    )
    ec2_resource = resource("ec2", "us-east-1")
    response = ec2_resource.create_instances(
        ImageId="ami_id",
        MinCount=1,
        MaxCount=1,
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {"VolumeSize": 50, "DeleteOnTermination": False},
            }
        ],
    )
    instance_id_document = json.dumps(
        ec2_utils.generate_instance_identity_document(response[0])
    )
    ecs.register_container_instance(
        cluster="UploadEventCluster", instanceIdentityDocument=instance_id_document
    )
    ecs.register_task_definition(
        family="kairon-task",
        taskRoleArn="arn:aws:iam::014936247795:role/ecsTaskExecutionRole",
        networkMode="awsvpc",
        containerDefinitions=[
            {
                "name": "kairon-task",
                "image": "digite/kairon-data-importer:latest",
                "cpu": 4096,
                "memory": 8192,
                "essential": True,
                "environment": [
                    {"name": "BOT", "value": "demo"},
                    {"name": "USER", "value": "demo"},
                    {"name": "IMPORT_DATA", "value": "demo"},
                    {"name": "OVERWRITE", "value": "demo"},
                ],
            },
        ],
        requiresCompatibilities=[
            "FARGATE",
        ],
        tags=[
            {"key": "Cost", "value": "AI"},
        ],
    )
    ec2 = client("ec2", region_name="us-east-1")
    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    # moto only sets the ENI private DNS name when the VPC has DNS hostnames.
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    subnet_id = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")["Subnet"]["SubnetId"]


def test_upload_event():
    os.environ["CONTAINER_NAME"] = "Test"
    os.environ[
        "CLUSTER"
    ] = "arn:aws:ecs:us-east-1:012345678910:cluster/UploadEventCluster"
    os.environ["TASK_DEFINITION"] = "kairon-task:1"
    os.environ["REGION_NAME"] = "us-east-1"
    os.environ["SECURITY_GROUPS"] = "sd-123456"
    os.environ["CONTAINER_NAME"] = "datat-upload"
    os.environ["SUBNETS"] = subnet_id
    request = [
        {"name": "BOT", "value": "5f64a80453cb9f7074054c62"},
        {"name": "USER", "value": "upload_user"},
        {"name": "IMPORT_DATA", "value": "--import-data"},
        {"name": "OVERWRITE", "value": "--overwrite"},
    ]
    response = generic.lambda_handler(request, {})
    assert response["body"] == "success"
    del os.environ["CLUSTER"]
    del os.environ["TASK_DEFINITION"]
    del os.environ["SUBNETS"]
    del os.environ["CONTAINER_NAME"]


def test_upload_event_2():
    os.environ["CONTAINER_NAME"] = "Test"
    os.environ[
        "CLUSTER"
    ] = "arn:aws:ecs:us-east-1:012345678910:cluster/UploadEventCluster"
    os.environ["TASK_DEFINITION"] = "kairon-task:1"
    os.environ["REGION_NAME"] = "us-east-1"
    os.environ["SECURITY_GROUPS"] = "sd-123456"
    os.environ["CONTAINER_NAME"] = "data-upload"
    os.environ["SUBNETS"] = subnet_id
    request = [
        {"name": "BOT", "value": "5f64a80453cb9f7074054c62"},
        {"name": "USER", "value": "upload_user"},
        {"name": "IMPORT_DATA", "value": ""},
        {"name": "OVERWRITE", "value": ""},
    ]
    response = generic.lambda_handler(request, {})
    assert response["body"] == "success"
    del os.environ["CLUSTER"]
    del os.environ["TASK_DEFINITION"]
    del os.environ["SUBNETS"]
    del os.environ["CONTAINER_NAME"]
