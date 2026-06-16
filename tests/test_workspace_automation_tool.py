"""Tests for the workspace automation management tool."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest

import mindroom.tools  # noqa: F401
from mindroom.config.main import Config
from mindroom.constants import RuntimePaths, resolve_runtime_paths
from mindroom.custom_tools import workspace_automation as workspace_automation_module
from mindroom.custom_tools.workspace_automation import WorkspaceAutomationTools
from mindroom.tool_system.metadata import SetupType, ToolCategory, ToolExecutionTarget, ToolStatus
from mindroom.tool_system.registry_state import TOOL_METADATA, TOOL_REGISTRY
from mindroom.tool_system.runtime_context import ToolRuntimeContext, tool_runtime_context
from mindroom.tool_system.worker_routing import agent_workspace_root_path
from mindroom.workspace_automations.service import (
    WorkspaceAutomationLoadedStatus,
    WorkspaceAutomationScanResult,
    WorkspaceAutomationService,
    get_active_workspace_automation_service,
    set_active_workspace_automation_service,
)
from tests.conftest import make_event_cache_mock

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def clear_active_workspace_automation_service() -> Iterator[None]:
    """Keep the process-global active service isolated between tests."""
    set_active_workspace_automation_service(None)
    yield
    set_active_workspace_automation_service(None)


@pytest.fixture
def runtime_paths(tmp_path: Path) -> RuntimePaths:
    """Create isolated runtime paths for tool tests."""
    return resolve_runtime_paths(
        config_path=tmp_path / "config.yaml",
        storage_path=tmp_path / "mindroom_data",
        process_env={
            "MATRIX_HOMESERVER": "http://localhost:8008",
            "MINDROOM_NAMESPACE": "",
        },
    )


def _config(runtime_paths: RuntimePaths) -> Config:
    return Config.validate_with_runtime(
        {
            "memory": {"backend": "none"},
            "agents": {
                "ops": {
                    "display_name": "Ops",
                    "rooms": ["Lobby"],
                    "workspace_automations": {
                        "enabled": True,
                        "allowed_actions": ["agent_message"],
                    },
                },
            },
        },
        runtime_paths,
    )


def _tool_context(runtime_paths: RuntimePaths) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        agent_name="ops",
        room_id="!room:localhost",
        thread_id="$thread:localhost",
        resolved_thread_id="$thread:localhost",
        requester_id="@user:localhost",
        client=AsyncMock(),
        config=_config(runtime_paths),
        runtime_paths=runtime_paths,
        conversation_cache=AsyncMock(),
        event_cache=make_event_cache_mock(),
        room=None,
    )


def _write_automations(workspace_root: Path) -> None:
    file_path = workspace_root / ".mindroom" / "automations.yaml"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        """
version: 1
automations:
  urgent_email_poll:
    schedule: "* * * * *"
    check:
      type: shell
      command: "true"
      timeout_seconds: 1
    trigger:
      exit_code: 42
    action:
      type: agent_message
      room: "Lobby"
      message: "Urgent email condition matched."
  too_slow:
    schedule: "* * * * *"
    check:
      type: shell
      command: "true"
      timeout_seconds: 999
    action:
      type: none
""",
        encoding="utf-8",
    )


class _FakeWorkspaceAutomationService:
    def __init__(self) -> None:
        self.scan_now_call_count = 0
        self._automations = (
            WorkspaceAutomationLoadedStatus(
                agent_name="ops",
                automation_id="urgent_email_poll",
                workspace_root="/workspace/ops",
                schedule="* * * * *",
                last_status="action_succeeded",
                last_run_at="2026-06-16T12:00:00+00:00",
                last_exit_code=42,
                last_error=None,
                last_event_id="$event:localhost",
            ),
        )

    @property
    def is_started(self) -> bool:
        return True

    def list_loaded(self) -> tuple[WorkspaceAutomationLoadedStatus, ...]:
        return self._automations

    async def scan_now(self) -> WorkspaceAutomationScanResult:
        self.scan_now_call_count += 1
        return WorkspaceAutomationScanResult(loaded_count=1, error_count=0)


@pytest.mark.asyncio
async def test_validate_automations_requires_tool_runtime_context() -> None:
    """Validation should fail clearly when no live tool runtime context exists."""
    payload = json.loads(await WorkspaceAutomationTools().validate_automations())

    assert payload["status"] == "error"
    assert payload["tool"] == "workspace_automation"
    assert payload["code"] == "unavailable"
    assert "tool runtime context" in payload["message"]


@pytest.mark.asyncio
async def test_validate_automations_scans_context_without_active_service(
    monkeypatch: pytest.MonkeyPatch,
    runtime_paths: RuntimePaths,
) -> None:
    """Validation should load configured targets from context without using the live service."""

    def fail_if_accessor_is_used() -> WorkspaceAutomationService | None:
        msg = "validate_automations must not use the active service accessor"
        raise AssertionError(msg)

    monkeypatch.setattr(
        workspace_automation_module,
        "get_active_workspace_automation_service",
        fail_if_accessor_is_used,
    )
    workspace_root = agent_workspace_root_path(runtime_paths.storage_root, "ops")
    _write_automations(workspace_root)

    with tool_runtime_context(_tool_context(runtime_paths)):
        payload = json.loads(await WorkspaceAutomationTools().validate_automations())

    assert payload["status"] == "ok"
    assert payload["loaded_count"] == 1
    assert payload["error_count"] == 1
    assert payload["automations"][0]["agent_name"] == "ops"
    assert payload["automations"][0]["automation_id"] == "urgent_email_poll"
    assert payload["automations"][0]["schedule"] == "* * * * *"
    assert payload["errors"][0]["automation_id"] == "too_slow"
    assert "timeout_seconds" in payload["errors"][0]["message"]


@pytest.mark.asyncio
async def test_list_automations_returns_unavailable_when_active_service_is_missing() -> None:
    """Listing should return a structured unavailable payload instead of raising."""
    assert get_active_workspace_automation_service() is None

    payload = json.loads(await WorkspaceAutomationTools().list_automations())

    assert payload["status"] == "error"
    assert payload["tool"] == "workspace_automation"
    assert payload["code"] == "unavailable"
    assert "Workspace automation service is unavailable" in payload["message"]


@pytest.mark.asyncio
async def test_list_automations_returns_statuses_from_active_service() -> None:
    """Listing should expose service status snapshots as JSON payloads."""
    service = _FakeWorkspaceAutomationService()
    set_active_workspace_automation_service(cast("WorkspaceAutomationService", service))

    payload = json.loads(await WorkspaceAutomationTools().list_automations())

    assert payload["status"] == "ok"
    assert payload["automations"] == [
        {
            "agent_name": "ops",
            "automation_id": "urgent_email_poll",
            "last_error": None,
            "last_event_id": "$event:localhost",
            "last_exit_code": 42,
            "last_run_at": "2026-06-16T12:00:00+00:00",
            "last_status": "action_succeeded",
            "schedule": "* * * * *",
            "workspace_root": "/workspace/ops",
        },
    ]


@pytest.mark.asyncio
async def test_reload_automations_scans_and_returns_updated_statuses() -> None:
    """Reloading should run a service scan and include fresh counts and loaded statuses."""
    service = _FakeWorkspaceAutomationService()
    set_active_workspace_automation_service(cast("WorkspaceAutomationService", service))

    payload = json.loads(await WorkspaceAutomationTools().reload_automations())

    assert service.scan_now_call_count == 1
    assert payload["status"] == "ok"
    assert payload["loaded_count"] == 1
    assert payload["error_count"] == 0
    assert payload["errors"] == []
    assert payload["automations"][0]["automation_id"] == "urgent_email_poll"


def test_workspace_automation_tool_metadata_is_registered() -> None:
    """The workspace automation tool should be registered with primary execution metadata."""
    assert "workspace_automation" in TOOL_METADATA
    assert "workspace_automation" in TOOL_REGISTRY

    metadata = TOOL_METADATA["workspace_automation"]
    assert metadata.category in {ToolCategory.PRODUCTIVITY, ToolCategory.DEVELOPMENT}
    assert metadata.status == ToolStatus.AVAILABLE
    assert metadata.setup_type == SetupType.NONE
    assert metadata.default_execution_target == ToolExecutionTarget.PRIMARY
    assert metadata.function_names == (
        "list_automations",
        "reload_automations",
        "validate_automations",
    )
    assert TOOL_REGISTRY["workspace_automation"]() is WorkspaceAutomationTools
