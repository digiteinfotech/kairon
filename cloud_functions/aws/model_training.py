from boto3 import client
import os
from json import loads

cluster = os.getenv("CLUSTER", 'default')
launch_type = os.getenv("LAUNCH_TYPE", 'default')
task_definition = os.getenv("CLUSTER", 'default')
capacity_provider = os.getenv("CAPACITY_PROVIDER", 'FARGATE_SPOT')
subnets = os.getenv("SUBNETS", "").split(",")


def handler(event, context):
    request_data = loads(event.body)
    ecs = client('ecs')
    response = ecs.run_task(
        capacityProviderStrategy=[
            {
                'capacityProvider': capacity_provider,
                'weight': 1,
                'base': 0
            },
        ],
        cluster=cluster,  # name of the cluster
        launchType=launch_type,
        taskDefinition=launch_type,  # replace with your task definition name and revision
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
    return str(response)
