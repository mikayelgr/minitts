# conftest.py is a special file in pytest that allows us to define fixtures
# and setup code that can be shared across multiple test files.

import sys
from typing import Any


# 1. Provide fake types_boto3_s3 to satisfy pydantic
class FakeTypesBoto3S3:
    S3Client: type[Any] = Any


sys.modules["types_boto3_s3"] = FakeTypesBoto3S3()
