import boto3
from botocore.exceptions import ClientError
import logging
from pydantic import validate_call, HttpUrl
from types_boto3_s3 import S3Client

logger = logging.getLogger(__name__)


@validate_call
def create_s3_client(
    aws_access_key_id: str,
    aws_secret_access_key: str,
    s3_endpoint_url: HttpUrl,
    s3_bucket: str,
) -> S3Client:
    aws_session = boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )

    logger.info("Connecting to S3")
    try:
        s3_resource = aws_session.resource("s3", endpoint_url=str(s3_endpoint_url))
        # Test access to the bucket at startup, will raise an error if it fails
        s3_resource.Bucket(s3_bucket).create()
    except ClientError as e:
        if e.response["Error"]["Code"] == "BucketAlreadyExists":
            logger.info(f"S3 bucket `{s3_bucket}` already exists.")
        else:
            logger.error(f"Unhandled S3 error occurred while accessing or creating bucket {s3_bucket}: {str(e)}")
            raise e

    try:
        s3_client = aws_session.client("s3", endpoint_url=str(s3_endpoint_url))
        if s3_client.get_public_access_block(Bucket=s3_bucket)["PublicAccessBlockConfiguration"]["BlockPublicAcls"]:
            # Ensure the bucket is publicly accessible by removing any public access blocks.
            r = s3_client.delete_public_access_block(Bucket=s3_bucket)
            if r["ResponseMetadata"]["HTTPStatusCode"] >= 200 and r["ResponseMetadata"]["HTTPStatusCode"] < 300:
                logger.info(f"Removed public access block from S3 bucket {s3_bucket}")
    except ClientError as e:
        if "notimplemented" in str(e).lower():
            logger.warning(f"S3 endpoint {s3_endpoint_url} does not support public access block configuration...")
            logger.info(f"Attempting to set ACL to public-read for bucket {s3_bucket} as fallback")
            try:
                s3_resource.Bucket(s3_bucket).Acl().put(ACL="public-read")
                logger.info(f"Set ACL to public-read for bucket {s3_bucket}")
            except:
                logger.error(
                    f"Failed to set ACL to public-read for bucket {s3_bucket}. This may cause issues with webhook callbacks accessing the audio files."
                )

        else:
            raise e

    logger.info("Connected to S3")
    return s3_client
