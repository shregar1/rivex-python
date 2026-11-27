"""Tests for the in-process feature-flag registry."""

from __future__ import annotations

import pytest

import rivex.flags as flags_module
from rivex.flags import FlagContext, FlagDefinition, is_enabled


@pytest.fixture(autouse=True)
def _reset():
    """Each test gets a fresh module-level registry."""
    flags_module.registry.clear()
    flags_module.registry.set_environment("development")
    yield


def test_unknown_flag_returns_false(_reset):
    assert is_enabled("missing") is False


def test_boolean_simple_on_and_off(_reset):
    flags_module.registry.set("a", True)
    flags_module.registry.set("b", False)
    assert is_enabled("a") is True
    assert is_enabled("b") is False


def test_dict_definition_is_parsed(_reset):
    flags_module.registry.set(
        "x",
        {
            "enabled": True,
            "tenant_overrides": {"t-1": False},
            "user_overrides": {"u-1": False},
        },
    )
    assert is_enabled("x") is True
    assert is_enabled("x", context={"tenant_id": "t-1"}) is False
    assert is_enabled("x", context={"user_id": "u-1"}) is False


def test_env_allowlist_blocks_other_envs(_reset):
    flags_module.registry.set(
        "prod-only",
        {"enabled": True, "environments": ["production"]},
    )
    flags_module.registry.set_environment("production")
    assert is_enabled("prod-only") is True
    flags_module.registry.set_environment("staging")
    assert is_enabled("prod-only") is False


def test_tenant_override_wins_over_percentage(_reset):
    flags_module.registry.set(
        "rollout",
        {
            "percentage_rollout": 50,
            "tenant_overrides": {"t-hot": True},
        },
    )
    assert is_enabled("rollout", context={"tenant_id": "t-hot"}) is True
    # A different tenant gets the rollout bucket — value unknown
    # but the call must return a bool.
    assert isinstance(
        is_enabled("rollout", context={"tenant_id": "t-other"}),
        bool,
    )


def test_percentage_rollout_is_stable_per_subject(_reset):
    flags_module.registry.set("ab", {"percentage_rollout": 50})
    for uid in [f"u-{i}" for i in range(50)]:
        first = is_enabled("ab", context={"user_id": uid})
        for _ in range(5):
            assert is_enabled("ab", context={"user_id": uid}) == first


def test_user_override_beats_default(_reset):
    flags_module.registry.set(
        "fx",
        {
            "enabled": True,
            "user_overrides": {"u-special": False},
        },
    )
    assert is_enabled("fx", context={"user_id": "u-other"}) is True
    assert is_enabled("fx", context={"user_id": "u-special"}) is False


def test_flag_definition_dataclass_round_trip():
    fd = FlagDefinition(
        enabled=True,
        percentage_rollout=20,
        environments=["prod", "staging"],
    )
    rebuilt = FlagDefinition.from_dict(fd.__dict__)
    assert rebuilt.enabled is True
    assert rebuilt.percentage_rollout == 20
    assert rebuilt.environments == ["prod", "staging"]


def test_flag_definition_dataclass_rejects_non_dict():
    with pytest.raises(TypeError):
        FlagDefinition.from_dict("not a dict")


def test_snapshot_is_a_copy(_reset):
    flags_module.registry.set("a", True)
    snap = flags_module.registry.snapshot()
    snap.pop("a")
    # The original registry still has the flag.
    assert is_enabled("a") is True


def test_clear_resets_state(_reset):
    flags_module.registry.set("a", True)
    flags_module.registry.clear()
    assert is_enabled("a") is False


def test_context_dataclass_helpers():
    ctx = FlagContext(tenant_id="t", user_id="u", environment="prod")
    assert ctx.to_dict() == {"tenant_id": "t", "user_id": "u", "environment": "prod"}


def test_module_level_helper(_reset):
    flags_module.registry.set("hello", True)
    assert is_enabled("hello") is True
