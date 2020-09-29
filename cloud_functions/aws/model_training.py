from boto3 import client
import os
import logging


def lambda_handler(event, context):
    cluster = os.getenv("CLUSTER", 'default')
    logging.info(cluster)
    task_definition = os.getenv("TASK_DEFINITION", 'default')
    capacity_provider = os.getenv("CAPACITY_PROVIDER", 'FARGATE_SPOT')
    subnets = os.getenv("SUBNETS", "").split(",")
    region_name = os.getenv("REGION_NAME", 'us-east-1')
    security_groups = os.getenv('SECURITY_GROUPS').split(",")
    container_name = os.getenv('CONTAINER_NAME')
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
            platformVersion='1.4.0',
            propagateTags="TASK_DEFINITION",
            tags=[{"key": "Cost", "value": "AI"}],
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'assignPublicIp': 'DISABLED',
                    'securityGroups': security_groups
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        "name": container_name,
                        'environment': [
                            {
                                'name': 'BOT',
                                'value': event['bot']
                            },
                            {
                                'name': 'USER',
                                'value': event['user']
                            }
                        ]
                    },
                ]
            },
        )
    except Exception as e:
        response = e
    return {"message": str(response)}
