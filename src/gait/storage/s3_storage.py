"""S3 storage backend using boto3."""
from __future__ import annotations

from io import BytesIO
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from gait.common.logging_utils import get_logger
from gait.storage.base import FileMetadata, Storage, StorageConfig

logger = get_logger(__name__)


class S3Storage(Storage):
    """AWS S3 storage backend."""

    def __init__(self, config: StorageConfig):
        """Initialize S3 storage.

        Args:
            config: StorageConfig with AWS credentials and bucket
        """
        self._config = config
        self._client = boto3.client(
            "s3",
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
        )
        self._bucket = config.bucket_name
        logger.info("s3.initialized", extra={"bucket": self._bucket, "region": config.region})

    def upload(
        self,
        file_path: str,
        file_content: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload bytes to S3."""
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=file_path,
                Body=file_content,
                ContentType=content_type,
                Metadata=metadata or {},
            )
            size_bytes = len(file_content)
            logger.info(
                "s3.upload",
                extra={"file_path": file_path, "size_bytes": size_bytes},
            )
            return FileMetadata(file_path, size_bytes, content_type)
        except ClientError as e:
            logger.error("s3.upload_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def upload_stream(
        self,
        file_path: str,
        file_stream,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload from stream to S3 using multipart upload."""
        try:
            config = boto3.s3.transfer.TransferConfig(
                multipart_threshold=5 * 1024 * 1024,  # 5 MB
                max_concurrency=10,
                multipart_chunksize=5 * 1024 * 1024,
                max_io_queue_size=100,
            )
            self._client.upload_fileobj(
                file_stream,
                self._bucket,
                file_path,
                ExtraArgs={"ContentType": content_type, "Metadata": metadata or {}},
                Config=config,
            )

            # Get file size from S3
            response = self._client.head_object(Bucket=self._bucket, Key=file_path)
            size_bytes = response["ContentLength"]

            logger.info(
                "s3.upload_stream",
                extra={"file_path": file_path, "size_bytes": size_bytes},
            )
            return FileMetadata(file_path, size_bytes, content_type)
        except ClientError as e:
            logger.error("s3.upload_stream_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def download(self, file_path: str) -> bytes:
        """Download file from S3."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=file_path)
            content = response["Body"].read()
            logger.info("s3.download", extra={"file_path": file_path, "size_bytes": len(content)})
            return content
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning("s3.not_found", extra={"file_path": file_path})
                raise FileNotFoundError(f"File not found: {file_path}")
            logger.error("s3.download_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def download_stream(self, file_path: str):
        """Download file from S3 as stream."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=file_path)
            stream = response["Body"]
            logger.info("s3.download_stream", extra={"file_path": file_path})
            return stream
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {file_path}")
            logger.error("s3.download_stream_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def delete(self, file_path: str) -> bool:
        """Delete file from S3."""
        try:
            if not self.exists(file_path):
                return False
            self._client.delete_object(Bucket=self._bucket, Key=file_path)
            logger.info("s3.deleted", extra={"file_path": file_path})
            return True
        except ClientError as e:
            logger.error("s3.delete_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def exists(self, file_path: str) -> bool:
        """Check if file exists in S3."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=file_path)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            return False

    def get_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """Get file metadata from S3."""
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=file_path)
            return FileMetadata(
                file_path,
                response["ContentLength"],
                response.get("ContentType", "application/octet-stream"),
                response.get("LastModified"),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error("s3.get_metadata_failed", extra={"file_path": file_path, "error": str(e)})
            return None

    def generate_presigned_url(
        self,
        file_path: str,
        expires_in_minutes: int = 60,
    ) -> str:
        """Generate presigned URL for S3 file."""
        try:
            if not self.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": file_path},
                ExpiresIn=expires_in_minutes * 60,
            )
            logger.info(
                "s3.presigned_url",
                extra={"file_path": file_path, "expires_in_minutes": expires_in_minutes},
            )
            return url
        except ClientError as e:
            logger.error(
                "s3.presigned_url_failed",
                extra={"file_path": file_path, "error": str(e)},
            )
            raise

    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[str]:
        """List files in S3 with optional prefix."""
        try:
            response = self._client.list_objects_v2(
                Bucket=self._bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )

            if "Contents" not in response:
                return []

            files = [obj["Key"] for obj in response["Contents"]]
            logger.info(
                "s3.list_files",
                extra={"prefix": prefix, "count": len(files)},
            )
            return files
        except ClientError as e:
            logger.error("s3.list_files_failed", extra={"prefix": prefix, "error": str(e)})
            raise

    def copy(self, source_path: str, dest_path: str) -> FileMetadata:
        """Copy file within S3."""
        try:
            if not self.exists(source_path):
                raise FileNotFoundError(f"Source file not found: {source_path}")

            copy_source = {"Bucket": self._bucket, "Key": source_path}
            self._client.copy_object(
                CopySource=copy_source,
                Bucket=self._bucket,
                Key=dest_path,
            )

            metadata = self.get_metadata(dest_path)
            if metadata is None:
                raise RuntimeError(f"Failed to copy file: {source_path} â†’ {dest_path}")

            logger.info(
                "s3.copied",
                extra={"source": source_path, "dest": dest_path},
            )
            return metadata
        except ClientError as e:
            logger.error(
                "s3.copy_failed",
                extra={"source": source_path, "dest": dest_path, "error": str(e)},
            )
            raise

    def close(self) -> None:
        """Close S3 client connection."""
        if self._client:
            self._client.close()
            logger.info("s3.closed")

