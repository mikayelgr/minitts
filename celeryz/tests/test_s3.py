from typing import cast
from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from pytest_mock import MockerFixture
from types_boto3_s3 import S3Client

from celeryz.s3 import create_s3_client


def test_create_s3_client_success(mocker: MockerFixture) -> None:
    mock_boto_session: MagicMock = mocker.patch("celeryz.s3.boto3.Session")
    mock_session_instance: MagicMock = MagicMock()
    mock_boto_session.return_value = mock_session_instance

    mock_resource: MagicMock = MagicMock()
    mock_session_instance.resource.return_value = mock_resource

    mock_client: S3Client = cast(S3Client, MagicMock())
    mock_session_instance.client.return_value = mock_client

    # Simulate a successful deletion of the public access block
    mock_client.get_public_access_block.return_value = {"PublicAccessBlockConfiguration": {"BlockPublicAcls": True}}
    mock_client.delete_public_access_block.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

    client: S3Client = create_s3_client("key", "secret", "http://s3", "my-bucket")

    mock_resource.Bucket.assert_called_with("my-bucket")
    mock_resource.Bucket().create.assert_called_once()
    mock_client.delete_public_access_block.assert_called_once_with(Bucket="my-bucket")
    assert client == mock_client


def test_create_s3_client_bucket_exists(mocker: MockerFixture) -> None:
    mock_boto_session: MagicMock = mocker.patch("celeryz.s3.boto3.Session")
    mock_session_instance: MagicMock = MagicMock()
    mock_boto_session.return_value = mock_session_instance

    mock_resource: MagicMock = MagicMock()
    mock_session_instance.resource.return_value = mock_resource

    # Simulate bucket already existing
    mock_resource.Bucket().create.side_effect = ClientError({"Error": {"Code": "BucketAlreadyExists"}}, "CreateBucket")

    mock_client: S3Client = cast(S3Client, MagicMock())
    mock_session_instance.client.return_value = mock_client
    mock_client.get_public_access_block.return_value = {"PublicAccessBlockConfiguration": {"BlockPublicAcls": False}}

    create_s3_client("key", "secret", "http://s3", "my-bucket")
    # Should not raise exception
