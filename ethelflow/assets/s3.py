import boto3
from botocore.client import Config
from ethelflow.settings.s3_settings import s3_settings


class S3Manager:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=s3_settings.endpoint_url,
            aws_access_key_id=s3_settings.access_key,
            aws_secret_access_key=s3_settings.secret_key,
            config=Config(signature_version="s3v4"),
        )
        self.bucket_name = s3_settings.bucket_name
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except self.s3_client.exceptions.ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                self.s3_client.create_bucket(Bucket=self.bucket_name)

    def upload_file(self, file_object, object_name):
        self.s3_client.upload_fileobj(file_object, self.bucket_name, object_name)
        return f"s3://{self.bucket_name}/{object_name}"

    def delete_file(self, object_name):
        self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)

    def download_file(self, object_name, file_object):
        self.s3_client.download_fileobj(self.bucket_name, object_name, file_object)


s3_manager = S3Manager()
