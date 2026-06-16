"""Tests for resolving workspace automation targets."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from mindroom.config.main import Config
from mindroom.constants import RuntimePaths, resolve_runtime_paths
from mindroom.runtime_resolution import resolve_agent_runtime as resolve_runtime
from mindroom.tool_system.worker_routing import agent_workspace_root_path
from mindroom.workspace_automations import targets
from mindroom.workspace_automations.targets import iter_workspace_automation_targets, resolve_action_room

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def runtime_paths(tmp_path: Path) -> RuntimePaths:
    """Create isolated runtime paths for target resolution."""
    return resolve_runtime_paths(
        config_path=tmp_path / "config.yaml",
        storage_path=tmp_path / "mindroom_data",
        process_env={
            "MATRIX_HOMESERVER": "http://localhost:8008",
            "MINDROOM_NAMESPACE": "",
        },
    )


def _config(runtime_paths: RuntimePaths, agents: dict[str, dict[str, object]]) -> Config:
    return Config.validate_with_runtime(
        {
            "memory": {"backend": "none"},
            "agents": agents,
        },
        runtime_paths,
    )


def test_shared_enabled_agents_are_returned_with_resolved_runtime_workspace_policy_and_rooms(
    runtime_paths: RuntimePaths,
) -> None:
    """Enabled shared agents should become complete automation targets."""
    config = _config(
        runtime_paths,
        {
            "ops": {
                "display_name": "Ops",
                "rooms": ["Lobby", "Ops"],
                "workspace_automations": {
                    "enabled": True,
                    "allowed_actions": ["agent_message"],
                },
            },
        },
    )

    result = iter_workspace_automation_targets(config, runtime_paths)

    expected_root = agent_workspace_root_path(runtime_paths.storage_root, "ops")
    assert len(result) == 1
    target = result[0]
    assert target.agent_name == "ops"
    assert target.agent_configured_rooms == ("Lobby", "Ops")
    assert target.policy.enabled is True
    assert target.policy.allowed_actions == ["agent_message"]
    assert target.agent_runtime.agent_name == "ops"
    assert target.agent_runtime.workspace is not None
    assert target.agent_runtime.workspace.root == expected_root
    assert target.workspace_root == expected_root
    assert expected_root.is_dir()


def test_disabled_agents_are_skipped(runtime_paths: RuntimePaths) -> None:
    """Policy-disabled agents should not become automation targets."""
    config = _config(
        runtime_paths,
        {
            "ops": {
                "display_name": "Ops",
                "workspace_automations": {"enabled": True},
            },
            "quiet": {
                "display_name": "Quiet",
                "workspace_automations": {"enabled": False},
            },
        },
    )

    result = iter_workspace_automation_targets(config, runtime_paths)

    assert [target.agent_name for target in result] == ["ops"]


def test_agents_with_no_workspace_after_resolution_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
    runtime_paths: RuntimePaths,
) -> None:
    """Targets should require a resolved usable workspace root."""
    config = _config(
        runtime_paths,
        {
            "ops": {
                "display_name": "Ops",
                "workspace_automations": {"enabled": True},
            },
        },
    )
    runtime_without_workspace = replace(
        resolve_runtime("ops", config, runtime_paths, execution_identity=None, create=True),
        workspace=None,
        tool_base_dir=None,
        file_memory_root=None,
    )

    def resolve_without_workspace(
        agent_name: str,
        _config: Config,
        _runtime_paths: RuntimePaths,
        execution_identity: object | None,
        *,
        create: bool = False,
    ) -> object:
        assert agent_name == "ops"
        assert execution_identity is None
        assert create is True
        return runtime_without_workspace

    monkeypatch.setattr(targets, "resolve_agent_runtime", resolve_without_workspace)

    result = iter_workspace_automation_targets(config, runtime_paths)

    assert result == []


def test_explicit_room_target_returns_that_room() -> None:
    """Explicit authored action rooms should be preserved for later Matrix resolution."""
    assert resolve_action_room(action_room="!ops:example.org", agent_configured_rooms=["Lobby"]) == "!ops:example.org"


def test_single_configured_room_fallback_returns_that_room() -> None:
    """Omitted action rooms should inherit a single configured room."""
    assert resolve_action_room(action_room=None, agent_configured_rooms=["Lobby"]) == "Lobby"


def test_multi_room_ambiguity_returns_none() -> None:
    """Omitted action rooms should not guess between multiple configured rooms."""
    assert resolve_action_room(action_room=None, agent_configured_rooms=["Lobby", "Ops"]) is None


def test_no_room_or_missing_room_ambiguity_returns_none() -> None:
    """Omitted action rooms should not invent a room when none are configured."""
    assert resolve_action_room(action_room=None, agent_configured_rooms=[]) is None


def test_private_agents_are_skipped_with_a_clear_reason(
    caplog: pytest.LogCaptureFixture,
    runtime_paths: RuntimePaths,
) -> None:
    """Private agents should be reported as unsupported automation targets."""
    config = _config(
        runtime_paths,
        {
            "mind": {
                "display_name": "Mind",
                "private": {"per": "user"},
                "workspace_automations": {"enabled": True},
            },
        },
    )
    caplog.set_level("INFO", logger="mindroom.workspace_automations.targets")

    result = iter_workspace_automation_targets(config, runtime_paths)

    assert result == []
    assert "Skipping workspace automation target for private agent 'mind'" in caplog.text
    assert "private workspace automations are not supported yet" in caplog.text


def test_disabled_private_agents_do_not_log_private_unsupported_reason(
    caplog: pytest.LogCaptureFixture,
    runtime_paths: RuntimePaths,
) -> None:
    """Disabled private agents should be skipped as disabled without unsupported-private noise."""
    config = _config(
        runtime_paths,
        {
            "mind": {
                "display_name": "Mind",
                "private": {"per": "user"},
                "workspace_automations": {"enabled": False},
            },
        },
    )
    caplog.set_level("INFO", logger="mindroom.workspace_automations.targets")

    result = iter_workspace_automation_targets(config, runtime_paths)

    assert result == []
    assert "private workspace automations are not supported yet" not in caplog.text
