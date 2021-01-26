import os

import boto3
from boto.exception import S3ResponseError


class FileUploader:
    @staticmethod
    def upload_file(file, bucket):
        """
        Uploads the selected file to a specific bucket in Amazon Simple Storage Service

        :param file: file
        :param bucket: s3 bucket
        :return: None
        """
        session = boto3.Session()
        s3 = session.client("s3")
        if not FileUploader.__check_bucket_exist(s3, bucket):
            s3.create_bucket(bucket)
        s3.upload_file(file, bucket, os.path.basename(file))

    @staticmethod
    def __check_bucket_exist(s3, bucket_name):
        try:
            if type(bucket_name) == str:
                s3.head_bucket(s3.Bucket(bucket_name))
            elif type(bucket_name) == s3.Bucket:
                s3.head_bucket(bucket_name)
            response = True
        except S3ResponseError:
            response = False
        return response