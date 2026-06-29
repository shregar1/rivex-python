"""
Infrastructure helpers for WebRTC: TURN server configuration and deployment.

Provides:
- ``TurnConfig`` — structured TURN server config (Coturn, etc.)
- ``TurnDeployment`` — generate configuration files for popular TURN servers
- ``generate_turn_config()`` — produce a list of ``IceServer`` from config
"""

from __future__ import annotations

import json
import os
from typing import Any

from rivex_adapter.webrtc.core import IceServer

# ---------------------------------------------------------------------------
# TURN Configuration
# ---------------------------------------------------------------------------


class TurnConfig:
    """Structured configuration for a TURN server.

    Can be serialised to Coturn config format or cloud TURN provider
    configuration (Twilio, Metered, Xirsys).

    Usage::

        config = TurnConfig(
            realm="example.com",
            listening_port=3478,
            tls_listening_port=5349,
            users={"user1": "password1"},
            use_auth_secret=True,
            auth_secret="my-secret",
        )
        coturn_conf = config.to_coturn_config()
        ice_servers = config.to_ice_servers()
    """

    def __init__(
        self,
        realm: str = "example.com",
        listening_ip: str = "0.0.0.0",
        listening_port: int = 3478,
        tls_listening_port: int = 5349,
        relay_ip: str = "",
        relay_threads: int = 0,
        min_port: int = 49152,
        max_port: int = 65535,
        users: dict[str, str] | None = None,
        use_auth_secret: bool = False,
        auth_secret: str = "",
        fingerprint: bool = True,
        lt_cred_mech: bool = True,
        log_file: str = "/var/log/turnserver.log",
        pid_file: str = "/var/run/turnserver.pid",
        certificate: str = "",
        private_key: str = "",
        tls_version: str = "1.2",
        verbose: bool = False,
    ):
        self.realm = realm
        self.listening_ip = listening_ip
        self.listening_port = listening_port
        self.tls_listening_port = tls_listening_port
        self.relay_ip = relay_ip
        self.relay_threads = relay_threads
        self.min_port = min_port
        self.max_port = max_port
        self.users = users or {}
        self.use_auth_secret = use_auth_secret
        self.auth_secret = auth_secret
        self.fingerprint = fingerprint
        self.lt_cred_mech = lt_cred_mech
        self.log_file = log_file
        self.pid_file = pid_file
        self.certificate = certificate
        self.private_key = private_key
        self.tls_version = tls_version
        self.verbose = verbose

    def to_coturn_config(self) -> str:
        """Generate a Coturn configuration file content."""
        lines = [
            f"listening-port={self.listening_port}",
            f"tls-listening-port={self.tls_listening_port}",
            f"listening-ip={self.listening_ip}",
            f"relay-ip={self.relay_ip}" if self.relay_ip else "",
            f"relay-threads={self.relay_threads}" if self.relay_threads else "",
            f"min-port={self.min_port}",
            f"max-port={self.max_port}",
            f"realm={self.realm}",
            f"fingerprint={'true' if self.fingerprint else 'false'}",
            f"lt-cred-mech={'true' if self.lt_cred_mech else 'false'}",
            f"log-file={self.log_file}",
            f"pid-file={self.pid_file}",
            f"cert={self.certificate}" if self.certificate else "",
            f"pkey={self.private_key}" if self.private_key else "",
            f"no-tlsv1" if self.tls_version == "1.2" else "",
            f"no-tlsv1_1" if self.tls_version == "1.2" else "",
            f"verbose" if self.verbose else "",
        ]

        if self.use_auth_secret and self.auth_secret:
            lines.append(f"use-auth-secret")
            lines.append(f"static-auth-secret={self.auth_secret}")
        else:
            for user, password in self.users.items():
                lines.append(f"user={user}:{password}")

        return "\n".join(line for line in lines if line)

    def to_ice_servers(
        self,
        urls: list[str] | None = None,
    ) -> list[IceServer]:
        """Generate a list of ``IceServer`` from this config.

        Args:
            urls: TURN URLs. Defaults to standard ports.

        Returns:
            List of ``IceServer`` objects for use with ``WebRTCConfig``.
        """
        if urls is None:
            urls = [
                f"turn:{self.listening_ip}:{self.listening_port}",
                f"turns:{self.listening_ip}:{self.tls_listening_port}",
            ]

        if self.use_auth_secret and self.auth_secret:
            return [IceServer(urls, username="webrtc", credential=self.auth_secret)]

        servers = []
        for user, password in self.users.items():
            servers.append(IceServer(urls, username=user, credential=password))
        return servers if servers else [IceServer(urls)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON export."""
        return {
            "realm": self.realm,
            "listening_ip": self.listening_ip,
            "listening_port": self.listening_port,
            "tls_listening_port": self.tls_listening_port,
            "min_port": self.min_port,
            "max_port": self.max_port,
            "use_auth_secret": self.use_auth_secret,
            "fingerprint": self.fingerprint,
            "lt_cred_mech": self.lt_cred_mech,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TurnConfig:
        """Deserialize from a dict."""
        return cls(**{k: v for k, v in d.items() if k in cls.__init__.__code__.co_varnames})


# ---------------------------------------------------------------------------
# TurnDeployment (cloud provider integrations)
# ---------------------------------------------------------------------------


class TurnDeployment:
    """Generate TURN credentials for common cloud TURN providers.

    Usage::

        # Coturn static config
        deploy = TurnDeployment.coturn(
            realm="example.com",
            users={"user1": "pass1"},
        )
        config = deploy.config
        coturn_file = deploy.generate_config_file()

        # Twilio-like (static config, user provides token endpoint)
        twilio = TurnDeployment(
            urls=["turn:global.turn.twilio.com:3478"],
            credential_type="token",
        )

        # Metered TURN
        metered = TurnDeployment.metered(api_key="...")
    """

    def __init__(
        self,
        urls: list[str] | None = None,
        credential_type: str = "static",
        config: TurnConfig | None = None,
    ):
        self.urls = urls or []
        self.credential_type = credential_type
        self.config = config or TurnConfig()

    @classmethod
    def coturn(
        cls,
        realm: str = "example.com",
        users: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TurnDeployment:
        """Create a Coturn deployment configuration."""
        config = TurnConfig(realm=realm, users=users or {}, **kwargs)
        return cls(
            urls=[f"turn:localhost:{config.listening_port}"],
            credential_type="static",
            config=config,
        )

    @classmethod
    def metered(cls, api_key: str) -> TurnDeployment:
        """Create a Metered TURN deployment configuration.

        Metered provides a REST API for credential generation.
        Returns a config with the standard Metered TURN URLs.
        """
        return cls(
            urls=[
                "turn:turn.metered.live:3478",
                "turns:turn.metered.live:5349",
            ],
            credential_type="rest",
            config=TurnConfig(
                use_auth_secret=True,
                auth_secret=api_key,
                realm="metered",
            ),
        )

    def generate_config_file(self, filepath: str = "turnserver.conf") -> None:
        """Write the Coturn configuration file."""
        with open(filepath, "w") as f:
            f.write(self.config.to_coturn_config())
            f.write("\n")

    def get_ice_servers(self) -> list[IceServer]:
        """Get IceServer list for use with WebRTCConfig."""
        return self.config.to_ice_servers(self.urls)


# ---------------------------------------------------------------------------
# Convenience: generate IceServer list from TURN config
# ---------------------------------------------------------------------------


def generate_turn_config(
    urls: str | list[str],
    username: str | None = None,
    credential: str | None = None,
    config_file: str | None = None,
) -> list[IceServer]:
    """Generate a list of ``IceServer`` for WebRTC configuration.

    Args:
        urls: TURN server URL(s) like ``"turn:turn.example.com:3478"``.
        username: Optional TURN username.
        credential: Optional TURN credential (password or HMAC key).
        config_file: Optional path to a Coturn config file to parse.

    Returns:
        A list with a single ``IceServer`` (or more if parsing from file).
    """
    servers: list[IceServer] = []

    if config_file and os.path.exists(config_file):
        parsed = _parse_coturn_config(config_file)
        for user, password in parsed.get("users", {}).items():
            servers.append(IceServer(
                urls or [f"turn:{parsed['listening_ip']}:{parsed['listening_port']}"],
                username=user,
                credential=password,
            ))

    if not servers:
        servers.append(IceServer(
            urls if isinstance(urls, list) else [urls],
            username=username,
            credential=credential,
        ))

    return servers


def _parse_coturn_config(filepath: str) -> dict[str, Any]:
    """Parse a Coturn configuration file.

    Extracts realm, listening IP/port, and user credentials.
    """
    result: dict[str, Any] = {
        "realm": "example.com",
        "listening_ip": "0.0.0.0",
        "listening_port": 3478,
        "users": {},
    }

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key == "realm":
                    result["realm"] = value
                elif key == "listening-ip":
                    result["listening_ip"] = value
                elif key == "listening-port":
                    result["listening_port"] = int(value)
                elif key == "user" and ":" in value:
                    user, _, password = value.partition(":")
                    result["users"][user] = password

    return result


__all__ = [
    "TurnConfig",
    "TurnDeployment",
    "generate_turn_config",
]
