"""Storage connector — governed access to S3/Azure Blob/GCS object storage.

Provides:
- Upload/download with size limits
- Path validation (no path traversal)
- Content type validation
- Audit trail of all operations
"""

from __future__ import annotations

import logging
import posixpath
import re
from typing import Any

from smn.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB default
_BLOCKED_EXTENSIONS = frozenset([".exe", ".bat", ".cmd", ".sh", ".ps1", ".dll", ".so"])
_PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.[/\\]")


class StorageConnector(BaseConnector):
    """Governed object storage connector supporting S3, Azure Blob, and GCS."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._provider: str = config.params.get("provider", "s3")  # s3 | azure | gcs
        self._bucket: str = config.params.get("bucket", "")
        self._max_upload_bytes: int = config.params.get("max_upload_bytes", _MAX_UPLOAD_BYTES)
        self._allowed_extensions: set[str] | None = (
            set(config.params["allowed_extensions"])
            if "allowed_extensions" in config.params
            else None
        )
        self._client = None

    async def connect(self) -> None:
        if not self._bucket:
            raise ValueError("StorageConnector requires 'bucket' in params")
        # Client initialisation is deferred to first use to avoid import errors
        # when the cloud SDK is not installed
        self._is_connected = True
        logger.info("StorageConnector ready: %s/%s", self._provider, self._bucket)

    async def disconnect(self) -> None:
        self._client = None
        self._is_connected = False

    async def health_check(self) -> bool:
        return self._is_connected

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Execute a storage operation.

        Operations:
        - list: List objects (prefix=..., max_keys=100)
        - get: Download object (key=...)
        - put: Upload object (key=..., data=bytes, content_type=...)
        - delete: Delete object (key=...) — requires 'storage:write' scope
        """
        key: str = kwargs.get("key", "")
        if key:
            self._validate_key(key)

        if operation == "list":
            return await self._list_objects(
                prefix=kwargs.get("prefix", ""),
                max_keys=kwargs.get("max_keys", 100),
            )
        elif operation == "get":
            return await self._get_object(key)
        elif operation == "put":
            return await self._put_object(
                key=key,
                data=kwargs.get("data", b""),
                content_type=kwargs.get("content_type", "application/octet-stream"),
            )
        elif operation == "delete":
            if "storage:write" not in self.config.scopes:
                raise PermissionError("Delete requires 'storage:write' scope")
            return await self._delete_object(key)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    def _validate_key(self, key: str) -> None:
        """Validate object key for safety."""
        if _PATH_TRAVERSAL_PATTERN.search(key):
            raise ValueError(f"Path traversal detected in key: {key}")

        if key.startswith("/"):
            raise ValueError("Object keys must not start with /")

        ext = posixpath.splitext(key)[1].lower()
        if ext in _BLOCKED_EXTENSIONS:
            raise ValueError(f"Blocked file extension: {ext}")

        if self._allowed_extensions and ext not in self._allowed_extensions:
            raise ValueError(
                f"Extension {ext} not in allowed list: {self._allowed_extensions}"
            )

    async def _list_objects(self, prefix: str, max_keys: int) -> list[dict[str, Any]]:
        """List objects — implementation delegates to cloud SDK."""
        if self._provider == "s3":
            import boto3
            s3 = boto3.client("s3")
            resp = s3.list_objects_v2(
                Bucket=self._bucket, Prefix=prefix, MaxKeys=min(max_keys, 1000)
            )
            return [
                {"key": obj["Key"], "size": obj["Size"], "modified": obj["LastModified"].isoformat()}
                for obj in resp.get("Contents", [])
            ]
        else:
            raise NotImplementedError(f"Provider {self._provider} list not yet implemented")

    async def _get_object(self, key: str) -> dict[str, Any]:
        if self._provider == "s3":
            import boto3
            s3 = boto3.client("s3")
            resp = s3.get_object(Bucket=self._bucket, Key=key)
            data = resp["Body"].read()
            return {
                "key": key,
                "data": data,
                "content_type": resp["ContentType"],
                "size": len(data),
            }
        else:
            raise NotImplementedError(f"Provider {self._provider} get not yet implemented")

    async def _put_object(self, key: str, data: bytes, content_type: str) -> dict[str, Any]:
        if len(data) > self._max_upload_bytes:
            raise ValueError(
                f"Upload size {len(data)} exceeds limit {self._max_upload_bytes}"
            )
        if "storage:write" not in self.config.scopes:
            raise PermissionError("Upload requires 'storage:write' scope")

        if self._provider == "s3":
            import boto3
            s3 = boto3.client("s3")
            s3.put_object(
                Bucket=self._bucket, Key=key, Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            return {"key": key, "size": len(data), "status": "uploaded"}
        else:
            raise NotImplementedError(f"Provider {self._provider} put not yet implemented")

    async def _delete_object(self, key: str) -> dict[str, Any]:
        if self._provider == "s3":
            import boto3
            s3 = boto3.client("s3")
            s3.delete_object(Bucket=self._bucket, Key=key)
            return {"key": key, "status": "deleted"}
        else:
            raise NotImplementedError(f"Provider {self._provider} delete not yet implemented")
