from boto3 import client
import os
from json import loads


def lambda_handler(event, context):
    cluster = os.getenv("CLUSTER", 'default')
    task_definition = os.getenv("TASK_DEFINITION", 'default')
    capacity_provider = os.getenv("CAPACITY_PROVIDER", 'FARGATE_SPOT')
    subnets = os.getenv("SUBNETS", "").split(",")
    region_name = os.getenv("REGION_NAME", 'us-east-1')
    request_data = loads(event['body'])
    ecs = client('ecs', region_name=region_name)
    try:
        response = ecs.run_task(
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
            platformVersion='LATEST',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'assignPublicIp': 'DISABLED'
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        'environment': [
                            {
                                'name': 'BOT',
                                'value': request_data['bot']
                            },
                            {
                                'name': 'USER',
                                'value': request_data['user']
                            }
                        ]
                    },
                ]
            },
        )
    except Exception as e:
        response = e
    return str(response)
