"""MinIO storage backend (S3-compatible object storage)."""
from __future__ import annotations

from typing import Optional

from minio import Minio
from minio.error import S3Error

from gait.common.logging_utils import get_logger
from gait.storage.base import FileMetadata, Storage, StorageConfig

logger = get_logger(__name__)


class MinIOStorage(Storage):
    """MinIO object storage backend (S3-compatible)."""

    def __init__(self, config: StorageConfig):
        """Initialize MinIO storage.

        Args:
            config: StorageConfig with MinIO endpoint, access key, secret key
        """
        self._config = config
        self._client = Minio(
            endpoint=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.use_ssl,
            region=config.region,
        )
        self._bucket = config.bucket_name

        # Ensure bucket exists
        self._ensure_bucket_exists()
        logger.info("minio.initialized", extra={"bucket": self._bucket, "endpoint": config.endpoint})

    def _ensure_bucket_exists(self) -> None:
        """Create bucket if it doesn't exist."""
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("minio.bucket_created", extra={"bucket": self._bucket})
        except S3Error as e:
            logger.warning("minio.bucket_check_failed", extra={"bucket": self._bucket, "error": str(e)})

    def upload(
        self,
        file_path: str,
        file_content: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload bytes to MinIO."""
        try:
            from io import BytesIO

            file_stream = BytesIO(file_content)
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=file_path,
                data=file_stream,
                length=len(file_content),
                content_type=content_type,
                metadata=metadata or {},
            )
            logger.info(
                "minio.upload",
                extra={"file_path": file_path, "size_bytes": len(file_content)},
            )
            return FileMetadata(file_path, len(file_content), content_type)
        except S3Error as e:
            logger.error("minio.upload_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def upload_stream(
        self,
        file_path: str,
        file_stream,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload from stream to MinIO."""
        try:
            # Read stream to get size
            stream_content = file_stream.read()
            from io import BytesIO

            stream = BytesIO(stream_content)
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=file_path,
                data=stream,
                length=len(stream_content),
                content_type=content_type,
                metadata=metadata or {},
            )
            logger.info(
                "minio.upload_stream",
                extra={"file_path": file_path, "size_bytes": len(stream_content)},
            )
            return FileMetadata(file_path, len(stream_content), content_type)
        except S3Error as e:
            logger.error("minio.upload_stream_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def download(self, file_path: str) -> bytes:
        """Download file from MinIO."""
        try:
            response = self._client.get_object(self._bucket, file_path)
            content = response.read()
            response.close()
            response.release_conn()
            logger.info("minio.download", extra={"file_path": file_path, "size_bytes": len(content)})
            return content
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning("minio.not_found", extra={"file_path": file_path})
                raise FileNotFoundError(f"File not found: {file_path}")
            logger.error("minio.download_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def download_stream(self, file_path: str):
        """Download file from MinIO as stream."""
        try:
            response = self._client.get_object(self._bucket, file_path)
            logger.info("minio.download_stream", extra={"file_path": file_path})
            return response
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {file_path}")
            logger.error("minio.download_stream_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def delete(self, file_path: str) -> bool:
        """Delete file from MinIO."""
        try:
            if not self.exists(file_path):
                return False
            self._client.remove_object(self._bucket, file_path)
            logger.info("minio.deleted", extra={"file_path": file_path})
            return True
        except S3Error as e:
            logger.error("minio.delete_failed", extra={"file_path": file_path, "error": str(e)})
            raise

    def exists(self, file_path: str) -> bool:
        """Check if file exists in MinIO."""
        try:
            self._client.stat_object(self._bucket, file_path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey" or "Not Found" in str(e):
                return False
            return False

    def get_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """Get file metadata from MinIO."""
        try:
            obj_stat = self._client.stat_object(self._bucket, file_path)
            return FileMetadata(
                file_path,
                obj_stat.size,
                obj_stat.content_type or "application/octet-stream",
                obj_stat.last_modified,
            )
        except S3Error as e:
            if e.code == "NoSuchKey" or "Not Found" in str(e):
                return None
            logger.error("minio.get_metadata_failed", extra={"file_path": file_path, "error": str(e)})
            return None

    def generate_presigned_url(
        self,
        file_path: str,
        expires_in_minutes: int = 60,
    ) -> str:
        """Generate presigned URL for MinIO file."""
        try:
            if not self.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            from datetime import timedelta

            url = self._client.get_presigned_download_url(
                self._bucket,
                file_path,
                expires=timedelta(minutes=expires_in_minutes),
            )
            logger.info(
                "minio.presigned_url",
                extra={"file_path": file_path, "expires_in_minutes": expires_in_minutes},
            )
            return url
        except S3Error as e:
            logger.error(
                "minio.presigned_url_failed",
                extra={"file_path": file_path, "error": str(e)},
            )
            raise

    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[str]:
        """List files in MinIO with optional prefix."""
        try:
            objects = self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            files = [obj.object_name for obj in objects][:max_keys]
            logger.info(
                "minio.list_files",
                extra={"prefix": prefix, "count": len(files)},
            )
            return files
        except S3Error as e:
            logger.error("minio.list_files_failed", extra={"prefix": prefix, "error": str(e)})
            raise

    def copy(self, source_path: str, dest_path: str) -> FileMetadata:
        """Copy file within MinIO."""
        try:
            if not self.exists(source_path):
                raise FileNotFoundError(f"Source file not found: {source_path}")

            copy_source = f"/{self._bucket}/{source_path}"
            self._client.copy_object(
                bucket_name=self._bucket,
                object_name=dest_path,
                copy_source=copy_source,
            )

            metadata = self.get_metadata(dest_path)
            if metadata is None:
                raise RuntimeError(f"Failed to copy file: {source_path} â†’ {dest_path}")

            logger.info(
                "minio.copied",
                extra={"source": source_path, "dest": dest_path},
            )
            return metadata
        except S3Error as e:
            logger.error(
                "minio.copy_failed",
                extra={"source": source_path, "dest": dest_path, "error": str(e)},
            )
            raise

    def close(self) -> None:
        """Close MinIO connection."""
        logger.info("minio.closed")

