"""Adapter MinIO (S3-compatible) — implémentation concrète d'`ObjectStoragePort`.

Au MVP, on s'appuie sur aioboto3 + l'API S3. Le serveur MinIO local est lancé
par `make up` (cf. specs/05-infrastructure.md §4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import aioboto3  # type: ignore[import-untyped]
import structlog
from botocore.exceptions import ClientError
from road2track_core.errors import StorageError

logger = structlog.get_logger(__name__)


class MinioObjectStorage:
    """Implémente `road2track_core.ports.ObjectStoragePort`.

    Note : on n'hérite pas formellement du Protocol — la duck-typing Pydantic / Python
    suffit. Tests d'isomorphisme via mypy/pyright.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        # MinIO accepte juste host:port ; il faut explicitement le préfixe http:// pour aioboto3.
        self._endpoint_url = (
            endpoint_url if endpoint_url.startswith(("http://", "https://"))
            else f"http://{endpoint_url}"
        )
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._session: Any = aioboto3.Session()

    def _client(self) -> Any:  # noqa: ANN401 — aioboto3 sans stubs
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )

    async def ensure_bucket(self, bucket: str) -> None:
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=bucket)
            except ClientError as e:
                response: dict[str, Any] = cast(dict[str, Any], e.response)
                error_section: dict[str, Any] = response.get("Error", {})
                code: str = str(error_section.get("Code", ""))
                if code in {"404", "NoSuchBucket"}:
                    logger.info("creating bucket", bucket=bucket)
                    await s3.create_bucket(Bucket=bucket)
                else:
                    raise StorageError(f"head_bucket failed: {e}") from e

    async def upload_file(self, local_path: Path, bucket: str, key: str) -> int:
        size = local_path.stat().st_size
        async with self._client() as s3:
            await s3.upload_file(str(local_path), bucket, key)
        logger.debug("uploaded", bucket=bucket, key=key, bytes=size)
        return size

    async def upload_bytes(self, data: bytes, bucket: str, key: str) -> int:
        """Upload direct depuis la mémoire (utile pour trajectory.json, manifests, ...)."""
        async with self._client() as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=data)
        size = len(data)
        logger.debug("uploaded bytes", bucket=bucket, key=key, bytes=size)
        return size

    async def download_file(self, bucket: str, key: str, local_path: Path) -> int:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._client() as s3:
            await s3.download_file(bucket, key, str(local_path))
        size = local_path.stat().st_size
        logger.debug("downloaded", bucket=bucket, key=key, bytes=size)
        return size

    async def download_directory(
        self, bucket: str, key_prefix: str, local_dir: Path
    ) -> tuple[int, int]:
        """Télécharge récursivement tous les objets sous `key_prefix` vers `local_dir`."""
        local_dir.mkdir(parents=True, exist_ok=True)
        prefix = key_prefix.rstrip("/") + "/"

        file_count = 0
        total_bytes = 0
        async with self._client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                contents: list[dict[str, Any]] = page.get("Contents", []) or []
                for obj in contents:
                    key: str = obj["Key"]
                    relative: str = key[len(prefix) :]
                    if not relative:
                        continue
                    target: Path = local_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    await s3.download_file(bucket, key, str(target))
                    file_count += 1
                    total_bytes += int(obj.get("Size", 0))
        logger.info(
            "downloaded directory",
            bucket=bucket,
            prefix=prefix,
            file_count=file_count,
            total_bytes=total_bytes,
        )
        return file_count, total_bytes

    async def upload_directory(
        self, local_dir: Path, bucket: str, key_prefix: str
    ) -> tuple[int, int]:
        if not local_dir.is_dir():
            raise StorageError(f"not a directory: {local_dir}")

        await self.ensure_bucket(bucket)
        prefix = key_prefix.rstrip("/")

        file_count = 0
        total_bytes = 0
        for path in local_dir.rglob("*"):
            if path.is_file():
                relative = path.relative_to(local_dir).as_posix()
                key = f"{prefix}/{relative}"
                total_bytes += await self.upload_file(path, bucket, key)
                file_count += 1

        logger.info(
            "uploaded directory",
            bucket=bucket,
            prefix=prefix,
            file_count=file_count,
            total_bytes=total_bytes,
        )
        return file_count, total_bytes
