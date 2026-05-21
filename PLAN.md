# ISSUE-225 — Implementation plan

## Goal
Ensure voice-message bursts coalesce into one agent turn even when a prior reply is already in flight.

## Invariant
N user voice messages from the same user on the same `(room, thread)` inside one debounce/grace window produce exactly one coalesced agent turn whose batched prompt mentions all N transcriptions, regardless of whether a prior reply is in flight on the thread.
Commands, hook-dispatched synthetic events, and scheduled fires continue to bypass coalescing as today.

## Code changes
`src/mindroom/turn_controller.py`:
- Fix 1: narrow `_should_bypass_coalescing_for_active_thread_follow_up` so `VOICE_SOURCE_KIND` returns `False`.
- Fix 2: add `VISIBLE_ROUTER_VOICE_ECHO_KEY = "com.mindroom.visible_router_voice_echo"` near the existing Matrix content metadata keys.
- Fix 2: set `VISIBLE_ROUTER_VOICE_ECHO_KEY: True` in `_visible_router_voice_echo_extra_content`.
- Fix 2: add a guard in `_dispatch_prepared_text_like_ingress` that marks visible router voice echoes handled and returns before interactive handling or enqueue.

## Test changes
`tests/test_turn_controller.py`:
- Unit: active-thread voice stays normal and flushes one coalesced batch containing both transcriptions.
- Unit: visible router voice echo is display-only.
- Unit: real trusted router handoff still dispatches.
- Unit: command, hook, and scheduled bypasses remain.

## Out of scope
- Voice attachment-context propagation in `response_runner.py` / `inbound_turn_normalizer.py`.
- Voice ingress serialization in `bot.py` `_create_task_wrapper`.
- H4 attachment "eviction", which was refuted and is actually thread-history truncation.

## Risks
- Coalescing gate drain loop releasing the queue between dispatches; live test will catch this.
- `VOICE_SOURCE_KIND` constant import path.
- Marker key collision with existing `m.relates_to` / extra-content schema.

## Verification commands
- `uv run pytest tests/test_turn_controller.py -k "voice or coalesc" -v`
- `uv run pytest tests/test_coalescing.py -v`
- `uv run pytest tests/ -k "not slow and not live" -x`
