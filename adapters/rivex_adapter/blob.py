"""
Blob storage adapters for S3, GCS, and Azure Blob Storage.

All adapters follow the same async interface::

    async with BlobStorageAdapter(url="s3://bucket/key") as store:
        await store.upload(b"data", "key.txt")
        data = await store.download("key.txt")
        await store.delete("key.txt")

Each adapter is auto-registered by ``import rivex_adapter``.
"""

from __future__ import annotations

from typing import Any, AsyncIterator


class BlobStorageAdapter:
    """Base class for blob storage adapters."""

    def __init__(self, url: str, **kwargs: Any):
        self.url = url
        self._kwargs = kwargs
        self._client: Any = None

    async def __aenter__(self) -> BlobStorageAdapter:
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the connection."""

    async def disconnect(self) -> None:
        """Close the connection."""

    async def upload(self, data: bytes, key: str, **kwargs: Any) -> None:
        """Upload *data* to *key*."""
        raise NotImplementedError

    async def download(self, key: str, **kwargs: Any) -> bytes:
        """Download *key* as bytes."""
        raise NotImplementedError

    async def delete(self, key: str, **kwargs: Any) -> None:
        """Delete *key*."""
        raise NotImplementedError

    async def exists(self, key: str, **kwargs: Any) -> bool:
        """Check if *key* exists."""
        raise NotImplementedError

    async def list(self, prefix: str = "", **kwargs: Any) -> list[str]:
        """List keys under *prefix*."""
        raise NotImplementedError


class S3BlobAdapter(BlobStorageAdapter):
    """S3-compatible object storage via ``aioboto3``.

    URL format: ``s3://access_key:secret_key@endpoint/bucket``
    """

    async def connect(self) -> None:
        import aioboto3

        parts = self.url.replace("s3://", "").split("/", 1)
        self._bucket = parts[1] if len(parts) > 1 else parts[0]
        self._session = aioboto3.Session(
            aws_access_key_id=self._kwargs.get("access_key"),
            aws_secret_access_key=self._kwargs.get("secret_key"),
        )
        endpoint = self._kwargs.get("endpoint")
        self._client = await self._session.client(
            "s3",
            endpoint_url=endpoint,
            **{k: v for k, v in self._kwargs.items() if k not in ("access_key", "secret_key", "endpoint")},
        ).__aenter__()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)

    async def upload(self, data: bytes, key: str, **kwargs: Any) -> None:
        await self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **kwargs)

    async def download(self, key: str, **kwargs: Any) -> bytes:
        resp = await self._client.get_object(Bucket=self._bucket, Key=key, **kwargs)
        body = await resp["Body"].read()
        return body

    async def delete(self, key: str, **kwargs: Any) -> None:
        await self._client.delete_object(Bucket=self._bucket, Key=key, **kwargs)

    async def exists(self, key: str, **kwargs: Any) -> bool:
        try:
            await self._client.head_object(Bucket=self._bucket, Key=key, **kwargs)
            return True
        except self._client.exceptions.ClientError:
            return False

    async def list(self, prefix: str = "", **kwargs: Any) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, **kwargs):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys


class GcsBlobAdapter(BlobStorageAdapter):
    """Google Cloud Storage via ``google-cloud-storage``.

    URL format: ``gcs://project_id/bucket``
    """

    async def connect(self) -> None:
        from google.cloud import storage

        self._client = storage.AsyncClient(project=self._kwargs.get("project"))
        parts = self.url.replace("gcs://", "").split("/", 1)
        self._bucket_name = parts[1] if len(parts) > 1 else parts[0]
        self._bucket = self._client.bucket(self._bucket_name)

    async def disconnect(self) -> None:
        await self._client.close()

    async def upload(self, data: bytes, key: str, **kwargs: Any) -> None:
        blob = self._bucket.blob(key)
        await blob.upload_from_string(data, **kwargs)

    async def download(self, key: str, **kwargs: Any) -> bytes:
        blob = self._bucket.blob(key)
        return await blob.download_as_bytes(**kwargs)

    async def delete(self, key: str, **kwargs: Any) -> None:
        blob = self._bucket.blob(key)
        await blob.delete(**kwargs)

    async def exists(self, key: str, **kwargs: Any) -> bool:
        blob = self._bucket.blob(key)
        return await blob.exists(**kwargs)

    async def list(self, prefix: str = "", **kwargs: Any) -> list[str]:
        keys: list[str] = []
        async for blob in self._client.list_blobs(self._bucket_name, prefix=prefix, **kwargs):
            keys.append(blob.name)
        return keys


class AzureBlobAdapter(BlobStorageAdapter):
    """Azure Blob Storage via ``azure-storage-blob``.

    URL format: ``azureblob://container_name``

    Requires ``connection_string`` as a kwarg.
    """

    async def connect(self) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        conn_str = self._kwargs.get("connection_string", "")
        self._service = BlobServiceClient.from_connection_string(conn_str)
        parts = self.url.replace("azureblob://", "")
        self._container = parts.split("/")[0]
        self._container_client = self._service.get_container_client(self._container)

    async def disconnect(self) -> None:
        await self._service.close()

    async def upload(self, data: bytes, key: str, **kwargs: Any) -> None:
        blob_client = self._container_client.get_blob_client(key)
        await blob_client.upload_blob(data, overwrite=True, **kwargs)

    async def download(self, key: str, **kwargs: Any) -> bytes:
        blob_client = self._container_client.get_blob_client(key)
        stream = await blob_client.download_blob(**kwargs)
        return await stream.readall()

    async def delete(self, key: str, **kwargs: Any) -> None:
        blob_client = self._container_client.get_blob_client(key)
        await blob_client.delete_blob(**kwargs)

    async def exists(self, key: str, **kwargs: Any) -> bool:
        blob_client = self._container_client.get_blob_client(key)
        return await blob_client.exists(**kwargs)

    async def list(self, prefix: str = "", **kwargs: Any) -> list[str]:
        keys: list[str] = []
        async for blob in self._container_client.list_blobs(name_starts_with=prefix, **kwargs):
            keys.append(blob.name)
        return keys
