# Outbound Redaction Report

## Scope

- Validated Matrix-visible tool trace previews, user-facing provider exceptions, and direct config command output.
- Built from current `origin/main` after PR #1176, which disables chat `!config` by default.
- Did not re-enable chat config commands.
- Did not change credentials API policy for explicit dashboard secret-return flows such as `include_value=true`.

## Confirmed Findings

- SECRETS-SECRETS-1 was real.
- Tool argument and result previews were built from raw values in `src/mindroom/tool_system/events.py`.
- These previews flow into `ToolTraceEntry` and Matrix `io.mindroom.tool_trace` metadata.
- SECRETS-SECRETS-2 was real.
- `get_user_friendly_error_message()` returned provider exception strings directly for auth and generic error paths.
- CONFIG-CONFIG-7 was real for direct config command handling.
- `handle_config_command("show")`, `get`, and set previews displayed authored config values directly.
- SECRETS-SECRETS-5 was real.
- Central redaction did not handle key/value list shapes such as `{"name": "OPENAI_API_KEY", "value": "plain"}`.

## Fixes

- `src/mindroom/redaction.py` now redacts value slots when sibling `name`, `key`, `header`, or related label fields identify a secret-bearing key.
- `src/mindroom/tool_system/events.py` now redacts tool args and results before preview construction and defensively redacts raw trace entries before Matrix metadata and prompt-context rendering.
- `src/mindroom/error_handling.py` now redacts user-facing exception text and the logged exception repr passed through this helper.
- `src/mindroom/commands/config_commands.py` now redacts config display values while keeping raw values only in confirmation state.

## Validation

- Red subset failed before production changes with nine expected leak failures.
- Focused tests after fixes: `python3 -m uv run pytest tests/test_redaction.py tests/test_tool_events.py tests/test_error_handling.py tests/test_config_commands.py --no-cov -n 0 -q`.
- Focused lint after fixes: `python3 -m uv run ruff check src/mindroom/redaction.py src/mindroom/tool_system/events.py src/mindroom/error_handling.py src/mindroom/commands/config_commands.py tests/test_redaction.py tests/test_tool_events.py tests/test_error_handling.py tests/test_config_commands.py`.

## Residual Risk

- SECRETS-SECRETS-6 remains report-only.
- `src/mindroom/api/credentials.py` still has explicit dashboard secret-returning flows such as `include_value=true` and edit-route credential payloads.
- Changing that behavior is product/API policy, not a small outbound-redaction helper patch.
