"""
``rivex-adapter`` — optional database driver bundle for Rivex, plus
messaging / queue, blob storage, and WebRTC adapters.

Installing this package registers all supported database drivers
with ``rivex.db`` so URL scheme detection works without per-driver
imports::

    pip install rivex-adapter

    from rivex import Rivex

    app = Rivex()
    app.db.configure("default", url="postgresql://user:pass@localhost/db")
    app.db.configure("cache", url="redis://localhost:6379/0")

Queue and blob adapters are available as standalone classes::

    from rivex_adapter.messaging import SqsAdapter, KafkaAdapter
    from rivex_adapter.blob import S3BlobAdapter, GcsBlobAdapter, AzureBlobAdapter

WebRTC adapters provide peer connection management, signaling,
and data channels::

    from rivex_adapter.webrtc import WebRTCPeerConnection, WebRTCSignaling
"""

from __future__ import annotations

import rivex_adapter.asyncpg  # noqa: F401
import rivex_adapter.redis  # noqa: F401
import rivex_adapter.motor  # noqa: F401
import rivex_adapter.aiomysql  # noqa: F401
import rivex_adapter.s3  # noqa: F401
