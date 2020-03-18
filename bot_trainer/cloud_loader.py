import boto3
import os

class FileUploader:

    @staticmethod
    def upload_File(self, file, bucket):
        session = boto3.Session()
        s3 = session.client('s3')
        if not FileUploader.__check_bucket_exist(s3, bucket):
            s3.create_bucket(bucket)
        s3.upload_file(file, bucket, os.path.basename(file))

    @staticmethod
    def __check_bucket_exist(self, s3, bucket_name):
        try:
            if type(bucket_name) == str:
                s3.head_bucket(s3.Bucket(bucket_name))
            elif type(bucket_name) == s3.Bucket:
                s3.head_bucket(bucket_name)
            response = True
        except:
            response = False
        return response
