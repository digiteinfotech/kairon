import os
from json import dumps

import moto
from boto3 import client

from cloud_functions.aws import model_training


@moto.mock_ecs
def test_model_training():
    ecs = client('ecs', region_name="us-east-1")
    ecs.create_cluster(
        clusterName='BotTrainerCluster',
        tags=[
            {
                'key': 'Cost',
                'value': 'AI'
            },
        ],
        capacityProviders=[
            'FARGATE',
        ]
    )
    ecs.register_task_definition(
        family='kairon-task',
        taskRoleArn='arn:aws:iam::014936247795:role/ecsTaskExecutionRole',
        networkMode='awsvpc',
        containerDefinitions=[
            {
                'name': 'kairon-task',
                'image': 'digite/kairon-task:latest',
                'cpu': 4096,
                'memory': 8192,
                'essential': True,
                'environment': [
                    {
                        'name': 'bot',
                        'value': 'demo'
                    },
                    {
                        'name': 'user',
                        'value': 'demo'
                    }
                ]
            },
        ],
        requiresCompatibilities=[
            'FARGATE',
        ],
        tags=[
            {
                'key': 'Cost',
                'value': 'AI'
            },
        ]
    )
    os.environ['CLUSTER'] = "arn:aws:ecs:us-east-1:012345678910:cluster/BotTrainerCluster"
    os.environ['TASK_DEFINITION'] = "kairon-task:1"
    os.environ['SUBNETS'] = "subnet-037df6ee62a8ac427,subnet-07a5cf356523a41c0,subnet-0e31d40f5be383435,subnet-06387a0b324a0e2b7,subnet-00714fa410157b038,subnet-0cd859c4a6087cf3b"
    response = model_training.lambda_handler({'body': dumps({'bot': 'sample', 'user': 'demo'})},{})
    del os.environ['CLUSTER']
    del os.environ['TASK_DEFINITION']
    del os.environ['SUBNETS']
    assert response
