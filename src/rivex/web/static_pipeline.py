from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any


class StaticPipeline:
    """Static file collection, versioning, compression, and CDN upload.

    Usage::

        pipeline = StaticPipeline(
            source_dirs=["app1/static", "app2/static"],
            output_dir="staticfiles",
        )
        pipeline.collect()
        pipeline.version()
        pipeline.compress()
        pipeline.upload_to_s3(bucket="my-bucket", prefix="static/")
    """

    def __init__(
        self,
        source_dirs: list[str] | None = None,
        output_dir: str = "staticfiles",
        manifest_path: str = "staticfiles/manifest.json",
    ):
        self._source_dirs = source_dirs or []
        self._output_dir = Path(output_dir)
        self._manifest_path = Path(manifest_path)
        self._manifest: dict[str, str] = {}

    def collect(self) -> int:
        """Copy all files from source directories to output directory."""
        count = 0
        self._output_dir.mkdir(parents=True, exist_ok=True)
        for src_dir in self._source_dirs:
            src = Path(src_dir)
            if not src.exists():
                continue
            for item in src.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(src)
                    target = self._output_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                    count += 1
        return count

    def version(self) -> dict[str, str]:
        """Generate content-hash filenames for all collected files.

        Returns the manifest mapping original paths to versioned paths.
        """
        self._manifest = {}
        if not self._output_dir.exists():
            return self._manifest

        for item in sorted(self._output_dir.rglob("*")):
            if not item.is_file():
                continue
            content = item.read_bytes()
            hash_digest = hashlib.sha256(content).hexdigest()[:12]
            rel = str(item.relative_to(self._output_dir))
            stem = item.stem
            ext = "".join(item.suffixes) if item.suffixes else ""
            # Insert hash before extension
            versioned_name = f"{stem}.{hash_digest}{ext}"
            versioned_path = item.parent / versioned_name
            if versioned_path.exists():
                versioned_path.unlink()
            item.rename(versioned_path)
            self._manifest[rel] = str(Path(rel).parent / versioned_name)

        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(json.dumps(self._manifest, indent=2))
        return dict(self._manifest)

    def compress(self, algorithms: list[str] | None = None) -> dict[str, list[str]]:
        """Compress static files. Returns ``{algorithm: [files]}``."""
        algorithms = algorithms or ["gzip"]
        results: dict[str, list[str]] = {alg: [] for alg in algorithms}
        import gzip

        for item in self._output_dir.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix in (".gz", ".br", ".map"):
                continue
            content = item.read_bytes()
            if "gzip" in algorithms:
                gz_path = item.with_suffix(item.suffix + ".gz")
                with gzip.open(gz_path, "wb") as f:
                    f.write(content)
                results["gzip"].append(str(gz_path))
        return results

    def load_manifest(self) -> dict[str, str]:
        """Read the manifest JSON from disk and return it as a copy.

        Replaces the in-memory ``self._manifest`` with whatever is on
        disk, so subsequent :meth:`resolve_url` lookups see the latest
        on-disk state. A shallow copy is returned so callers cannot
        accidentally mutate the internal cache.

        Returns:
            Mapping of original relative paths to their versioned
            filenames as recorded in ``self._manifest_path``. Empty
            when no manifest file exists.
        """
        if self._manifest_path.exists():
            self._manifest = json.loads(self._manifest_path.read_text())
        return dict(self._manifest)

    def resolve_url(self, path: str) -> str:
        """Resolve an original path to its versioned URL."""
        if not self._manifest:
            self.load_manifest()
        return self._manifest.get(path, path)

    async def upload_to_s3(
        self, bucket: str, prefix: str = "static/", region: str = "us-east-1"
    ) -> int:
        """Upload all files to S3-compatible storage."""
        import boto3

        s3 = boto3.client("s3", region_name=region)
        count = 0
        extra_args = {"CacheControl": "public, max-age=31536000, immutable"}
        for item in self._output_dir.rglob("*"):
            if item.is_file():
                key = prefix + str(item.relative_to(self._output_dir))
                content_type, _ = mimetypes.guess_type(str(item))
                if content_type:
                    extra_args["ContentType"] = content_type
                s3.upload_file(str(item), bucket, key, ExtraArgs=extra_args)
                count += 1
        return count

    async def upload_to_gcs(self, bucket: str, prefix: str = "static/") -> int:
        """Upload all files to Google Cloud Storage."""
        from google.cloud import storage

        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        count = 0
        for item in self._output_dir.rglob("*"):
            if item.is_file():
                blob = bucket_obj.blob(prefix + str(item.relative_to(self._output_dir)))
                blob.cache_control = "public, max-age=31536000, immutable"
                blob.upload_from_filename(str(item))
                count += 1
        return count

    async def upload_to_azure(self, container: str, prefix: str = "static/") -> int:
        """Upload all files to Azure Blob Storage."""
        from azure.storage.blob import BlobServiceClient

        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        service = BlobServiceClient.from_connection_string(conn_str)
        container_client = service.get_container_client(container)
        count = 0
        for item in self._output_dir.rglob("*"):
            if item.is_file():
                blob_client = container_client.get_blob_client(
                    prefix + str(item.relative_to(self._output_dir))
                )
                with open(item, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                count += 1
        return count
