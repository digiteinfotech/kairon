import os

from boto3 import client


def lambda_handler(event, context):
    cluster = os.getenv("CLUSTER")
    task_definition = os.getenv("TASK_DEFINITION")
    capacity_provider = os.getenv("CAPACITY_PROVIDER", 'FARGATE')
    subnets = os.getenv("SUBNETS", "").split(",")
    region_name = os.getenv("REGION_NAME")
    security_groups = os.getenv('SECURITY_GROUPS','').split(",")
    container_name = os.getenv('CONTAINER_NAME')
    ecs = client('ecs', region_name=region_name)
    print(os.environ)
    print(event)
    body=event
    if type(body) == dict:
        env_data = [body]
    else:
        env_data = body

    try:
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
        print(e)


    output = {
        "statusCode": 200,
        "statusDescription": "200 OK",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "text/html; charset=utf-8"
        },
        "body": response
    }
    return output
