import os
import json
import requests
from boto3 import client
from urllib.parse import urljoin


# file deepcode ignore W0703: Any Exception should be updated as status for Training Data processor
def lambda_handler(event, context):
    cluster = os.getenv("CLUSTER", 'default')
    task_definition = os.getenv("TASK_DEFINITION", 'default')
    capacity_provider = os.getenv("CAPACITY_PROVIDER", 'FARGATE_SPOT')
    subnets = os.getenv("SUBNETS", "").split(",")
    region_name = os.getenv("REGION_NAME", 'us-east-1')
    security_groups = os.getenv('SECURITY_GROUPS', '').split(",")
    container_name = os.getenv('CONTAINER_NAME')
    kairon_url = os.getenv('KAIRON_URL')
    ecs = client('ecs', region_name=region_name)
    print(event)
    body = json.loads(event['body'])
    if 'token' in body:
        try:
            env_data = [
                {
                    'name': 'TOKEN',
                    'value': body.get('token')
                },
                {
                    'name': 'USER',
                    'value': body.get('user')
                }
            ]
            if kairon_url and body.get('token'):
                status = {"status": "Creating ECS Task"}
                headers = {
                    'content-type': 'application/json',
                    'X-USER': body.get('user'),
                    'Authorization': 'Bearer ' + body.get('token')
                }
                requests.put(urljoin(kairon_url, "/update/data/generator/status"),
                             headers=headers,
                             json=status
                             )

            task_response = ecs.run_task(
                capacityProviderStrategy=[
                    {
                        'capacityProvider': capacity_provider,
                        'weight': 1,
                        'base': 0
                    },
                ],
                cluster=cluster,
                taskDefinition=task_definition,  # replace with your task definition name and revision
                count=1,
                platformVersion='1.4.0',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': subnets,
                        'assignPublicIp': 'ENABLED',
                        'securityGroups': security_groups
                    }
                },
                overrides={
                    'containerOverrides': [
                        {
                            "name": container_name,
                            'environment': env_data
                        },
                    ]
                },
            )
            print(task_response)
            response = "success"
        except Exception as e:
            response = str(e)
    else:
        response = "Invalid lambda handler request: authentication token is required"

    output = {
        "statusCode": 200,
        "statusDescription": "200 OK",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "text/html; charset=utf-8"
        },
        "body": response
    }
    if kairon_url and body.get('token'):
        status = {"status": response}
        headers = {
            'content-type': 'application/json',
            'X-USER': body.get('user'),
            'Authorization': 'Bearer ' + body.get('token')
        }
        requests.put(urljoin(kairon_url, "/update/data/generator/status"),
                     headers=headers,
                     json=status
                     )
    return output
