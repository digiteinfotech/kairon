from typing import Any

import ujson as json
import os
import time

from boto3 import Session
from botocore.exceptions import ClientError
from mongoengine import DoesNotExist

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass
from loguru import logger
from kairon.shared.data.constant import EVENT_STATUS, TASK_TYPE


class CloudUtility:

    @staticmethod
    def upload_file(file, bucket, output_filename=None):
        """
        Uploads the selected file to a specific bucket in Amazon Simple Storage Service

        :param file: file
        :param bucket: s3 bucket
        :param output_filename: file name (can contain sub directories in bucket)
        :param role: IAM role
        :return: None
        """
        session = Session()
        s3 = session.client("s3")
        if not CloudUtility.__check_bucket_exist(s3, bucket):
            s3.create_bucket(Bucket=bucket)
        if Utility.check_empty_string(output_filename):
            output_filename = os.path.basename(file)
        s3.upload_file(file, bucket, output_filename)
        return "https://{0}.s3.amazonaws.com/{1}".format(bucket, output_filename)

    @staticmethod
    def __check_bucket_exist(s3, bucket_name):
        """
        Checks whether the bucket exists.
        It is assumed that role supplied has permissions to perform the query and
        therefore the ClientError will only be thrown when bucket does not exists.
        """
        try:
            s3.head_bucket(Bucket=bucket_name)
            response = True
        except ClientError:
            response = False
        return response

    @staticmethod
    def delete_file(bucket, file):
        session = Session()
        s3 = session.client("s3")
        if CloudUtility.__check_bucket_exist(s3, bucket):
            s3.delete_object(Bucket=bucket, Key=file)

    @staticmethod
    def trigger_lambda(event_class: EventClass, env_data: Any, task_type: TASK_TYPE = TASK_TYPE.CALLBACK.value,
                       from_executor: bool = False):
        """
        Triggers lambda based on the event class.
        """
        start_time = time.time()
        region = Utility.environment['events']['executor'].get('region')
        if Utility.check_empty_string(region):
            region = "us-east-1"
        function = Utility.environment['events']['task_definition'][event_class]
        session = Session()
        lambda_client = session.client("lambda", region_name=region)
        response = {}
        executor_log_id = CloudUtility.log_task(event_class=event_class, task_type=task_type, data=env_data,
                                                status=EVENT_STATUS.INITIATED, from_executor=from_executor)
        try:
            response = lambda_client.invoke(
                FunctionName=function,
                InvocationType='RequestResponse',
                LogType='Tail',
                Payload=json.dumps(env_data).encode(),
            )
            response['Payload'] = json.loads(response['Payload'].read())
            logger.info(response)

            if CloudUtility.lambda_execution_failed(response):
                err = response['Payload'].get('body') or response
                raise AppException(err)
        except Exception as e:
            exception = str(e)
            CloudUtility.log_task(event_class=event_class, task_type=task_type, data=env_data,
                                  status=EVENT_STATUS.FAIL, response=response, executor_log_id=executor_log_id,
                                  elapsed_time=time.time() - start_time, exception=exception,
                                  from_executor=from_executor)
            raise AppException(exception)
        CloudUtility.log_task(event_class=event_class, task_type=task_type, data=env_data,
                              status=EVENT_STATUS.COMPLETED, response=response, executor_log_id=executor_log_id,
                              elapsed_time=time.time() - start_time, from_executor=from_executor)
        return response

    @staticmethod
    def log_task(event_class: EventClass, task_type: TASK_TYPE, data: dict, status: EVENT_STATUS, **kwargs):
        from bson import ObjectId
        from kairon.shared.events.data_objects import ExecutorLogs

        executor_log_id = kwargs.get("executor_log_id") if kwargs.get("executor_log_id") else ObjectId().__str__()
        bot_id = CloudUtility.get_bot_id_from_env_data(event_class, data,
                                                       from_executor=kwargs.get("from_executor", False),
                                                       task_type=task_type)
        if event_class == EventClass.scheduler_evaluator.value and not task_type:
            task_type = TASK_TYPE.CALLBACK.value
        try:
            log = ExecutorLogs.objects(executor_log_id=executor_log_id, task_type=task_type, event_class=event_class,
                                       status=EVENT_STATUS.INITIATED.value).get()
        except DoesNotExist:
            log = ExecutorLogs(executor_log_id=executor_log_id, task_type=task_type, event_class=event_class)

        log.data = data if data else log.data
        log.status = status if status else log.status

        for key, value in kwargs.items():
            if not getattr(log, key, None) and Utility.is_picklable_for_mongo({key: value}):
                setattr(log, key, value)
        log.bot = bot_id
        log.save()
        return executor_log_id

    @staticmethod
    def get_bot_id_from_env_data(event_class: EventClass, data: Any, **kwargs):
        bot = None
        from_executor = kwargs.get("from_executor")

        if isinstance(data, dict) and 'bot' in data:
            bot = data['bot']

        elif event_class == EventClass.web_search:
            bot = data.get('bot')

        elif event_class == EventClass.pyscript_evaluator:
            predefined_objects = data.get('predefined_objects', {})

            if 'slot' in predefined_objects and 'bot' in predefined_objects['slot']:
                bot = predefined_objects['slot']['bot']

            task_type = kwargs.get("task_type")
            if task_type == "Callback" and 'bot' in predefined_objects:
                bot = predefined_objects['bot']

        elif event_class == EventClass.scheduler_evaluator and isinstance(data, list):
            for item in data:
                if item.get('name') == 'PREDEFINED_OBJECTS':
                    predefined_objects = item.get('value', {})
                    if 'bot' in predefined_objects:
                        bot = predefined_objects['bot']
                        break

        elif from_executor and isinstance(data, list):
            for item in data:
                if item.get('name') == 'BOT':
                    bot = item.get('value')
                    break

        return bot

    @staticmethod
    def lambda_execution_failed(response):
        return (response['StatusCode'] != 200 or
                (response['Payload'].get('statusCode') and response['Payload']['statusCode'] != 200))
