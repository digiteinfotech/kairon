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
    request = {'requestContext': {'elb': {'targetGroupArn': 'arn:aws:elasticloadbalancing:us-east-1:730423251530:targetgroup/lambda-TX4lMDoYUZbApfgNrIbQ/4a615ec885b3df97'}}, 'httpMethod': 'POST', 'path': '/train', 'queryStringParameters': {}, 'headers': {'accept': '*/*', 'accept-encoding': 'gzip, deflate', 'accept-language': 'en-US,en;q=0.5', 'connection': 'keep-alive', 'content-length': '60', 'content-type': 'application/json', 'host': 'kairon-2115467540.us-east-1.elb.amazonaws.com', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:81.0) Gecko/20100101 Firefox/81.0', 'x-amzn-trace-id': 'Root=1-5f740d25-7880bfe721e19cf91613f209', 'x-forwarded-for': '103.203.145.3', 'x-forwarded-port': '80', 'x-forwarded-proto': 'http'}, 'body': '{  "bot": "5f64a80453cb9f7074054c62",  "user": "fshaikh"}', 'isBase64Encoded': False}
    response = model_training.lambda_handler(request,{})
    del os.environ['CLUSTER']
    del os.environ['TASK_DEFINITION']
    del os.environ['SUBNETS']
    assert response
