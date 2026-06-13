"""Abstract storage interface for file operations.

Implementations: S3, MinIO, local filesystem (for development).
This design allows swapping storage backends without changing business logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional


class StorageConfig:
    """Configuration for storage backends."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        endpoint: str,
        bucket_name: str,
        region: str = "us-east-1",
        use_ssl: bool = True,
        **kwargs,
    ):
        """Initialize storage config.

        Args:
            access_key: AWS/MinIO access key
            secret_key: AWS/MinIO secret key
            endpoint: S3 endpoint (s3.amazonaws.com for AWS, localhost:9000 for MinIO)
            bucket_name: Bucket name
            region: AWS region (default: us-east-1)
            use_ssl: Use HTTPS (default: True)
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.region = region
        self.use_ssl = use_ssl
        self.extra = kwargs


class FileMetadata:
    """Metadata for a stored file."""

    def __init__(
        self,
        file_path: str,
        size_bytes: int,
        content_type: str = "application/octet-stream",
        created_at: Optional[datetime] = None,
        modified_at: Optional[datetime] = None,
    ):
        """Initialize file metadata.

        Args:
            file_path: Unique file path/key in storage
            size_bytes: File size in bytes
            content_type: MIME type
            created_at: Creation timestamp
            modified_at: Last modification timestamp
        """
        self.file_path = file_path
        self.size_bytes = size_bytes
        self.content_type = content_type
        self.created_at = created_at or datetime.now(timezone.utc)
        self.modified_at = modified_at or datetime.now(timezone.utc)


class Storage(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    def upload(
        self,
        file_path: str,
        file_content: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload a file to storage.

        Args:
            file_path: Key/path to store file under (e.g., 'sessions/abc-123/video.mp4')
            file_content: File bytes
            content_type: MIME type
            metadata: Optional custom metadata dict

        Returns:
            FileMetadata with upload details
        """
        pass

    @abstractmethod
    def upload_stream(
        self,
        file_path: str,
        file_stream,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileMetadata:
        """Upload a file from a stream (memory-efficient for large files).

        Args:
            file_path: Key/path to store file under
            file_stream: File-like object with read() method
            content_type: MIME type
            metadata: Optional custom metadata dict

        Returns:
            FileMetadata with upload details
        """
        pass

    @abstractmethod
    def download(self, file_path: str) -> bytes:
        """Download a file from storage.

        Args:
            file_path: Key/path of file to download

        Returns:
            File bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    def download_stream(self, file_path: str):
        """Download a file as a stream (memory-efficient for large files).

        Args:
            file_path: Key/path of file to download

        Returns:
            File-like object with read() method

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    def delete(self, file_path: str) -> bool:
        """Delete a file from storage.

        Args:
            file_path: Key/path of file to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def exists(self, file_path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            file_path: Key/path to check

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    def get_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """Get file metadata without downloading.

        Args:
            file_path: Key/path of file

        Returns:
            FileMetadata or None if not found
        """
        pass

    @abstractmethod
    def generate_presigned_url(
        self,
        file_path: str,
        expires_in_minutes: int = 60,
    ) -> str:
        """Generate a presigned URL for temporary access.

        Args:
            file_path: Key/path of file
            expires_in_minutes: URL expiration time (default: 60 minutes)

        Returns:
            Presigned URL string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[str]:
        """List all files with optional prefix filter.

        Args:
            prefix: Filter files by prefix (e.g., 'sessions/abc-123/')
            max_keys: Maximum number of keys to return

        Returns:
            List of file paths
        """
        pass

    @abstractmethod
    def copy(self, source_path: str, dest_path: str) -> FileMetadata:
        """Copy a file within storage.

        Args:
            source_path: Source file key/path
            dest_path: Destination file key/path

        Returns:
            FileMetadata for copied file

        Raises:
            FileNotFoundError: If source doesn't exist
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close storage connections (optional cleanup)."""
        pass
