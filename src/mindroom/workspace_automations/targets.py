"""Workspace automation target resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mindroom.runtime_resolution import resolve_agent_runtime

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from mindroom.config.main import Config
    from mindroom.config.models import WorkspaceAutomationPolicyConfig
    from mindroom.constants import RuntimePaths
    from mindroom.runtime_resolution import ResolvedAgentRuntime

_LOGGER = logging.getLogger(__name__)
_PRIVATE_AGENT_SKIP_REASON = "private workspace automations are not supported yet"


@dataclass(frozen=True)
class WorkspaceAutomationTarget:
    """Resolved runtime target for one shared agent's workspace automations."""

    agent_name: str
    agent_configured_rooms: tuple[str, ...]
    policy: WorkspaceAutomationPolicyConfig
    agent_runtime: ResolvedAgentRuntime
    workspace_root: Path


def iter_workspace_automation_targets(
    config: Config,
    runtime_paths: RuntimePaths,
) -> list[WorkspaceAutomationTarget]:
    """Return shared agents with enabled automations and a resolved workspace."""
    targets: list[WorkspaceAutomationTarget] = []
    for agent_name, agent_config in config.agents.items():
        policy = config.get_agent_workspace_automation_policy(agent_name)
        if not policy.enabled:
            _LOGGER.debug(
                "Skipping workspace automation target for agent '%s': workspace automations are disabled.",
                agent_name,
            )
            continue

        if agent_config.private is not None:
            _LOGGER.info(
                "Skipping workspace automation target for private agent '%s': %s.",
                agent_name,
                _PRIVATE_AGENT_SKIP_REASON,
            )
            continue

        agent_runtime = resolve_agent_runtime(
            agent_name,
            config,
            runtime_paths,
            execution_identity=None,
            create=True,
        )
        if agent_runtime.workspace is None:
            _LOGGER.info(
                "Skipping workspace automation target for agent '%s': no usable workspace resolved.",
                agent_name,
            )
            continue

        targets.append(
            WorkspaceAutomationTarget(
                agent_name=agent_name,
                agent_configured_rooms=tuple(agent_config.rooms),
                policy=policy,
                agent_runtime=agent_runtime,
                workspace_root=agent_runtime.workspace.root,
            ),
        )

    return targets


def resolve_action_room(
    *,
    action_room: str | None,
    agent_configured_rooms: Sequence[str],
) -> str | None:
    """Resolve an authored action room without Matrix alias lookups."""
    if action_room is not None:
        return action_room
    if len(agent_configured_rooms) == 1:
        return agent_configured_rooms[0]
    return None


__all__ = [
    "WorkspaceAutomationTarget",
    "iter_workspace_automation_targets",
    "resolve_action_room",
]
