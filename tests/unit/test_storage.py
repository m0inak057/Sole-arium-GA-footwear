"""Unit tests for storage backends (src.gait.storage)."""
from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from gait.storage.base import FileMetadata, Storage, StorageConfig

# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture
def storage_config() -> StorageConfig:
    """Create a test storage config."""
    return StorageConfig(
        access_key="test-access",
        secret_key="test-secret",
        endpoint="s3.amazonaws.com",
        bucket_name="test-bucket",
        region="us-east-1",
        use_ssl=True,
    )


@pytest.fixture
def file_metadata() -> FileMetadata:
    """Create test file metadata."""
    return FileMetadata(
        file_path="test-file.mp4",
        size_bytes=1024000,
        content_type="video/mp4",
    )


# â”€â”€ FileMetadata Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFileMetadata:
    def test_create_metadata(self, file_metadata: FileMetadata):
        assert file_metadata.file_path == "test-file.mp4"
        assert file_metadata.size_bytes == 1024000
        assert file_metadata.content_type == "video/mp4"

    def test_metadata_timestamps_set(self, file_metadata: FileMetadata):
        assert file_metadata.created_at is not None
        assert file_metadata.modified_at is not None

    def test_metadata_default_content_type(self):
        metadata = FileMetadata("file.bin", 512)
        assert metadata.content_type == "application/octet-stream"


# â”€â”€ StorageConfig Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestStorageConfig:
    def test_create_config(self, storage_config: StorageConfig):
        assert storage_config.access_key == "test-access"
        assert storage_config.secret_key == "test-secret"
        assert storage_config.bucket_name == "test-bucket"

    def test_config_defaults(self):
        config = StorageConfig(
            access_key="key",
            secret_key="secret",
            endpoint="localhost:9000",
            bucket_name="bucket",
        )
        assert config.region == "us-east-1"
        assert config.use_ssl is True

    def test_config_custom_region(self):
        config = StorageConfig(
            access_key="key",
            secret_key="secret",
            endpoint="s3.eu-west-1.amazonaws.com",
            bucket_name="bucket",
            region="eu-west-1",
        )
        assert config.region == "eu-west-1"


# â”€â”€ S3Storage Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestS3Storage:
    @pytest.fixture
    def mock_s3_client(self):
        """Mock boto3 S3 client."""
        with patch("boto3.client") as mock:
            yield mock.return_value

    def test_upload(self, storage_config: StorageConfig, mock_s3_client):
        """Test uploading bytes to S3."""
        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            content = b"test file content"

            result = storage.upload(
                file_path="test.mp4",
                file_content=content,
                content_type="video/mp4",
            )

            assert result.file_path == "test.mp4"
            assert result.size_bytes == len(content)
            mock_s3_client.put_object.assert_called_once()

    def test_download(self, storage_config: StorageConfig, mock_s3_client):
        """Test downloading file from S3."""
        content = b"downloaded content"
        mock_response = MagicMock()
        mock_response.__getitem__ = lambda self, key: (
            MagicMock(read=lambda: content) if key == "Body" else None
        )
        mock_s3_client.get_object.return_value = mock_response

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            result = storage.download("test.mp4")

            assert result == content
            mock_s3_client.get_object.assert_called_once_with(
                Bucket="test-bucket",
                Key="test.mp4",
            )

    def test_exists_true(self, storage_config: StorageConfig, mock_s3_client):
        """Test file existence check when file exists."""
        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            assert storage.exists("test.mp4") is True

    def test_exists_false(self, storage_config: StorageConfig, mock_s3_client):
        """Test file existence check when file doesn't exist."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "404"}}
        mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            assert storage.exists("nonexistent.mp4") is False

    def test_delete(self, storage_config: StorageConfig, mock_s3_client):
        """Test deleting file from S3."""
        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            result = storage.delete("test.mp4")

            assert result is True
            mock_s3_client.delete_object.assert_called_once()

    def test_delete_nonexistent(self, storage_config: StorageConfig, mock_s3_client):
        """Test deleting file that doesn't exist."""
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": "404"}}
        mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            result = storage.delete("nonexistent.mp4")

            assert result is False

    def test_presigned_url(self, storage_config: StorageConfig, mock_s3_client):
        """Test generating presigned URL."""
        expected_url = "https://s3.amazonaws.com/bucket/file.mp4?signature"
        mock_s3_client.generate_presigned_url.return_value = expected_url

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            url = storage.generate_presigned_url("test.mp4", expires_in_minutes=60)

            assert url == expected_url
            mock_s3_client.generate_presigned_url.assert_called_once()

    def test_list_files(self, storage_config: StorageConfig, mock_s3_client):
        """Test listing files in S3."""
        files = ["file1.mp4", "file2.mp4", "file3.mp4"]
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [{"Key": f} for f in files]
        }

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            result = storage.list_files(prefix="sessions/")

            assert len(result) == 3
            assert result == files

    def test_copy_file(self, storage_config: StorageConfig, mock_s3_client):
        """Test copying file within S3."""
        mock_s3_client.head_object.return_value = {"ContentLength": 1024}
        mock_s3_client.copy_object.return_value = {}

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            result = storage.copy("source.mp4", "dest.mp4")

            assert result.file_path == "dest.mp4"
            mock_s3_client.copy_object.assert_called_once()


# â”€â”€ Factory Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestStorageFactory:
    def test_create_s3_storage(self, storage_config: StorageConfig):
        """Test creating S3 storage via factory."""
        with patch("boto3.client"):
            with patch("gait.storage.factory.S3Storage") as MockS3:
                MockS3.return_value = Mock(spec=Storage)
                from gait.storage.factory import create_storage
                create_storage("s3", storage_config)
                MockS3.assert_called_once_with(storage_config)

    def test_unsupported_backend(self, storage_config: StorageConfig):
        """Test error on unsupported backend."""
        with pytest.raises(ValueError, match="Unsupported storage backend"):
            from gait.storage.factory import create_storage
            create_storage("gcs", storage_config)

    def test_create_from_env(self):
        """Test creating storage from environment variables."""
        with patch.dict("os.environ", {
            "STORAGE_BACKEND": "s3",
            "S3_ACCESS_KEY": "env-key",
            "S3_SECRET_KEY": "env-secret",
            "S3_ENDPOINT": "s3.amazonaws.com",
            "S3_BUCKET_NAME": "env-bucket",
        }):
            with patch("boto3.client"):
                with patch("gait.storage.factory.S3Storage") as MockS3:
                    MockS3.return_value = Mock(spec=Storage)
                    from gait.storage.factory import create_storage_from_env
                    create_storage_from_env()
                    MockS3.assert_called_once()


# â”€â”€ Storage Interface Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestStorageInterface:
    def test_storage_is_abc(self):
        """Verify Storage is abstract."""
        with pytest.raises(TypeError):
            Storage()

    def test_context_manager(self, storage_config: StorageConfig):
        """Test context manager support."""
        with patch("boto3.client"):
            with patch("gait.storage.factory.S3Storage") as MockS3:
                mock_storage = Mock(spec=Storage)
                mock_storage.__enter__ = Mock(return_value=mock_storage)
                mock_storage.__exit__ = Mock(return_value=None)
                MockS3.return_value = mock_storage
                from gait.storage.factory import create_storage
                with create_storage("s3", storage_config) as storage:
                    assert storage is mock_storage

    def test_upload_stream_interface(self, storage_config: StorageConfig):
        """Test upload_stream method exists."""
        with patch("boto3.client"):
            with patch("gait.storage.factory.S3Storage") as MockS3:
                mock_storage = Mock(spec=Storage)
                MockS3.return_value = mock_storage
                from gait.storage.factory import create_storage
                storage = create_storage("s3", storage_config)
                assert hasattr(storage, "upload_stream")
                assert callable(storage.upload_stream)

    def test_download_stream_interface(self, storage_config: StorageConfig):
        """Test download_stream method exists."""
        with patch("boto3.client"):
            with patch("gait.storage.factory.S3Storage") as MockS3:
                mock_storage = Mock(spec=Storage)
                MockS3.return_value = mock_storage
                from gait.storage.factory import create_storage
                storage = create_storage("s3", storage_config)
                assert hasattr(storage, "download_stream")
                assert callable(storage.download_stream)

    def test_get_metadata_interface(self, storage_config: StorageConfig):
        """Test get_metadata method exists."""
        with patch("boto3.client"):
            with patch("gait.storage.factory.S3Storage") as MockS3:
                mock_storage = Mock(spec=Storage)
                MockS3.return_value = mock_storage
                from gait.storage.factory import create_storage
                storage = create_storage("s3", storage_config)
                assert hasattr(storage, "get_metadata")
                assert callable(storage.get_metadata)


# â”€â”€ Error Handling Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestErrorHandling:
    def test_download_file_not_found(self, storage_config: StorageConfig, mock_s3_client):
        """Test FileNotFoundError on missing file download."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "NoSuchKey"}}
        mock_s3_client.get_object.side_effect = ClientError(error_response, "GetObject")

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)

            with pytest.raises(FileNotFoundError):
                storage.download("nonexistent.mp4")

    def test_copy_source_not_found(self, storage_config: StorageConfig, mock_s3_client):
        """Test FileNotFoundError on copy with missing source."""
        from botocore.exceptions import ClientError
        error_response = {"Error": {"Code": "NoSuchKey"}}

        with patch("gait.storage.s3_storage.boto3.client", return_value=mock_s3_client):
            from gait.storage.s3_storage import S3Storage
            storage = S3Storage(storage_config)
            mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")

            with pytest.raises(FileNotFoundError):
                storage.copy("nonexistent.mp4", "dest.mp4")


@pytest.fixture(scope="session")
def mock_s3_client():
    """Session-scoped S3 client mock."""
    with patch("boto3.client") as mock:
        yield mock.return_value


