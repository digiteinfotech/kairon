import os

from boto3 import Session
from botocore.exceptions import ClientError

from kairon import Utility


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
        It is assumed that role supplied has permissions to perform the operation and
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
