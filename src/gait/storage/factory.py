"""Storage factory for creating storage backends."""
from __future__ import annotations

import os
from typing import Optional

from src.gait.common.logging_utils import get_logger
from src.gait.storage.base import Storage, StorageConfig
from src.gait.storage.s3_storage import S3Storage

logger = get_logger(__name__)


def create_storage(
    backend: str = "s3",
    config: Optional[StorageConfig] = None,
) -> Storage:
    """Create a storage backend instance.

    Args:
        backend: Storage type ("s3", "minio"). Default: "s3"
        config: StorageConfig. If None, loads from environment variables.

    Returns:
        Storage backend instance

    Raises:
        ValueError: If backend is unsupported or config is invalid
    """
    if config is None:
        config = StorageConfig(
            access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
            endpoint=os.getenv("S3_ENDPOINT", "s3.amazonaws.com"),
            bucket_name=os.getenv("S3_BUCKET_NAME", "gait-analysis"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            use_ssl=os.getenv("S3_USE_SSL", "true").lower() == "true",
        )

    backend_lower = backend.lower()

    if backend_lower == "s3":
        logger.info("storage.created", extra={"backend": "s3"})
        return S3Storage(config)
    elif backend_lower == "minio":
        # Lazy import to avoid minio dependency at module level
        from src.gait.storage.minio_storage import MinIOStorage
        logger.info("storage.created", extra={"backend": "minio"})
        return MinIOStorage(config)
    else:
        raise ValueError(f"Unsupported storage backend: {backend!r}. Supported: s3, minio")


def create_storage_from_env() -> Storage:
    """Create storage backend from environment variables.

    Environment variables:
        STORAGE_BACKEND: "s3" or "minio" (default: "s3")
        S3_ACCESS_KEY: Access key
        S3_SECRET_KEY: Secret key
        S3_ENDPOINT: Endpoint URL
        S3_BUCKET_NAME: Bucket name
        AWS_REGION: AWS region (default: us-east-1)
        S3_USE_SSL: Use HTTPS (default: true)

    Returns:
        Storage backend instance
    """
    backend = os.getenv("STORAGE_BACKEND", "s3")
    return create_storage(backend=backend)
