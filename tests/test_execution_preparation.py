"""Tests for history-message preparation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from defusedxml.ElementTree import fromstring

from mindroom.constants import ORIGINAL_SENDER_KEY
from mindroom.execution_preparation import _fallback_static_token_budget
from mindroom.prepared_conversation_chain import (
    build_matrix_prompt_with_thread_history,
    build_thread_history_chain,
    build_unseen_context_chain,
    collect_history_messages,
)
from tests.conftest import make_visible_message

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from agno.models.message import Message

    from mindroom.matrix.client_visible_messages import ResolvedVisibleMessage


def _build_unseen_context_messages(
    prompt: str,
    thread_history: Sequence[ResolvedVisibleMessage],
    *,
    seen_event_ids: set[str],
    current_event_id: str,
    active_event_ids: Collection[str],
    response_sender_id: str | None,
    current_sender_id: str | None = None,
) -> tuple[tuple[Message, ...], list[str]]:
    chain, unseen_event_ids = build_unseen_context_chain(
        prompt,
        thread_history,
        seen_event_ids=seen_event_ids,
        current_event_id=current_event_id,
        active_event_ids=active_event_ids,
        response_sender_id=response_sender_id,
        current_sender_id=current_sender_id,
    )
    return chain.messages, unseen_event_ids


def test_fallback_static_token_budget_preserves_context_window_bounds() -> None:
    """Fallback static budgeting should keep missing and reserve-clamped bounds."""
    assert _fallback_static_token_budget(context_window=None, reserve_tokens=100) is None
    assert _fallback_static_token_budget(context_window=0, reserve_tokens=100) is None
    assert _fallback_static_token_budget(context_window=1_000, reserve_tokens=800) == 500
    assert _fallback_static_token_budget(context_window=1_000, reserve_tokens=100) == 900


def test_fallback_thread_history_caps_long_messages_without_dropping_them() -> None:
    """Oversized Matrix fallback messages should stay in context with a capped body."""
    long_body = "x" * 201
    chain = build_thread_history_chain(
        "Current request",
        [
            make_visible_message(
                sender="@alice:localhost",
                body=long_body,
                event_id="$long",
            ),
        ],
        response_sender_id="@mindroom_team:localhost",
        max_message_length=200,
    )

    assert len(chain.messages) == 2
    assert chain.messages[0].role == "user"
    assert chain.messages[0].content == f"@alice:localhost: {'x' * 199}…"
    assert long_body not in str(chain.messages[0].content)
    assert chain.messages[1].content == "Current request"


def test_collect_history_messages_keeps_visible_body_only() -> None:
    """History collection should ignore Matrix tool-trace metadata and keep only the visible body."""
    messages = [
        make_visible_message(
            sender="@alice:localhost",
            body="Worked on it",
            content={"io.mindroom.tool_trace": {"version": 2, "events": [{"tool_name": "run_shell_command"}]}},
        ),
    ]

    collected = collect_history_messages(
        messages,
        max_messages=None,
        max_message_length=None,
        missing_sender_label=None,
    )

    assert collected == [("@alice:localhost", "Worked on it")]


def test_collect_history_messages_leaves_no_trace_messages_unchanged() -> None:
    """No-trace history collection should remain byte-identical to the prior output."""
    messages = [make_visible_message(sender="@alice:localhost", body="Earlier context")]

    collected = collect_history_messages(
        messages,
        max_messages=None,
        max_message_length=None,
        missing_sender_label=None,
    )

    assert collected == [("@alice:localhost", "Earlier context")]


def test_collect_history_messages_drops_tool_only_message() -> None:
    """Tool-only metadata should not be promoted into visible history context."""
    messages = [
        make_visible_message(
            sender="@alice:localhost",
            content={"io.mindroom.tool_trace": {"version": 2, "events": [{"tool_name": "run_shell_command"}]}},
        ),
    ]

    collected = collect_history_messages(
        messages,
        max_messages=None,
        max_message_length=None,
        missing_sender_label=None,
    )

    assert collected == []


def test_collect_history_messages_truncates_visible_body() -> None:
    """Length caps should apply only to the visible body content."""
    messages = [
        make_visible_message(
            sender="@alice:localhost",
            body="ok" * 20,
            content={"io.mindroom.tool_trace": {"version": 2, "events": [{"tool_name": "run_shell_command"}]}},
        ),
    ]

    collected = collect_history_messages(
        messages,
        max_messages=None,
        max_message_length=20,
        missing_sender_label=None,
    )

    assert collected[0][0] == "@alice:localhost"
    assert collected[0][1].startswith("okok")
    assert collected[0][1].endswith("…")
    assert len(collected[0][1]) == 20


def test_build_matrix_prompt_with_thread_history_truncates_visible_body_to_max_length() -> None:
    """Rendered Matrix history bodies should respect max_message_length using only visible text."""
    thread_history = [
        make_visible_message(
            sender="@alice:localhost",
            body="ok" * 200,
            content={"io.mindroom.tool_trace": {"version": 2, "events": [{"tool_name": "run_shell_command"}]}},
        ),
    ]

    prompt = build_matrix_prompt_with_thread_history(
        "Follow-up",
        thread_history,
        max_message_length=200,
    )

    parsed = fromstring(f"<root>{prompt}</root>")
    rendered_messages = parsed.findall(".//msg")
    assert rendered_messages[0].text is not None
    assert len(rendered_messages[0].text) == 200
    assert rendered_messages[0].text.endswith("…")


def test_unseen_context_keeps_self_sent_relayed_user_message() -> None:
    """A tool-relayed user message from the agent account should remain user context."""
    thread_history = [
        make_visible_message(
            sender="@mindroom_code:localhost",
            body="@mindroom_missing_agent Please investigate this",
            event_id="$spawn-root",
            content={
                "body": "@mindroom_missing_agent Please investigate this",
                ORIGINAL_SENDER_KEY: "@alice:localhost",
            },
        ),
        make_visible_message(
            sender="@alice:localhost",
            body="What happened?",
            event_id="$question",
        ),
    ]

    messages, unseen_event_ids = _build_unseen_context_messages(
        "What happened?",
        thread_history,
        seen_event_ids=set(),
        current_event_id="$question",
        active_event_ids=(),
        response_sender_id="@mindroom_code:localhost",
        current_sender_id="@alice:localhost",
    )

    assert unseen_event_ids == ["$spawn-root"]
    assert messages[0].role == "user"
    assert messages[0].content == "@alice:localhost: @mindroom_missing_agent Please investigate this"


def test_unseen_context_keeps_unpersisted_self_sent_message() -> None:
    """A self-sent Matrix event not known to persisted history should remain visible context."""
    thread_history = [
        make_visible_message(
            sender="@mindroom_code:localhost",
            body="@mindroom_missing_agent Please investigate this",
            event_id="$spawn-root",
        ),
        make_visible_message(
            sender="@alice:localhost",
            body="What happened?",
            event_id="$question",
        ),
    ]

    messages, unseen_event_ids = _build_unseen_context_messages(
        "What happened?",
        thread_history,
        seen_event_ids=set(),
        current_event_id="$question",
        active_event_ids=(),
        response_sender_id="@mindroom_code:localhost",
        current_sender_id="@alice:localhost",
    )

    assert unseen_event_ids == ["$spawn-root"]
    assert messages[0].role == "assistant"
    assert messages[0].content == "@mindroom_missing_agent Please investigate this"


def test_unseen_context_skips_persisted_self_sent_response_event() -> None:
    """A self-sent Matrix event already represented in persisted history should not be duplicated."""
    thread_history = [
        make_visible_message(
            sender="@mindroom_code:localhost",
            body="Persisted assistant answer",
            event_id="$answer",
        ),
        make_visible_message(
            sender="@alice:localhost",
            body="What next?",
            event_id="$question",
        ),
    ]

    messages, unseen_event_ids = _build_unseen_context_messages(
        "What next?",
        thread_history,
        seen_event_ids={"$answer"},
        current_event_id="$question",
        active_event_ids=(),
        response_sender_id="@mindroom_code:localhost",
        current_sender_id="@alice:localhost",
    )

    assert unseen_event_ids == []
    assert len(messages) == 1
    assert messages[0].content == 'Current message:\n<msg from="@alice:localhost"><![CDATA[What next?]]></msg>'
