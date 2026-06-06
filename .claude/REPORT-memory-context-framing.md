# Memory and MCP Context Framing Report

## Scope

Validated and fixed:

- MEMORY-MEMORY-1: retrieved chat-derived memories were replayed without an explicit untrusted-data boundary.
- MEMORY-MEMORY-2: retrieved file-memory entries and free-text snippets were replayed without provenance and trust framing.
- MCP-MCP-4: MCP tool results, tool descriptions, schemas, and OAuth bridge catalog server instructions were exposed without untrusted-output framing.

Validated only:

- Delegate/subagent follow-up low-priv to high-priv confusion.

## Confirmed Findings

### MEMORY-MEMORY-1

Confirmed.
`format_memories_as_context()` rendered retrieved memories as plain bullets.
Stored user chat could therefore reappear as model-visible context without saying it was untrusted user-provided data.

Fixed in `src/mindroom/memory/_prompting.py`.
Retrieved memories now include:

- an untrusted user-data boundary;
- source labels from `user_id`;
- memory IDs where available;
- normalized `data:` payload text.

### MEMORY-MEMORY-2

Confirmed.
File backend search results and free-text file snippets flow through the same memory formatter.
They now inherit the same untrusted boundary and provenance labels, including `source_file` and `line` when present.

Also fixed the file-memory entrypoint path in `build_memory_prompt_parts()`.
The entrypoint is now framed as untrusted user-provided file context before it is placed in the session preamble.

### MCP-MCP-4

Confirmed.
MCP result text and error text were passed through as raw `ToolResult.content` or `MCPToolCallError` messages.
MCP tool descriptions were exposed directly as provider-visible function descriptions.
OAuth bridge `list_tools` exposed server instructions and descriptions directly.

Fixed in `src/mindroom/mcp/results.py` and `src/mindroom/mcp/toolkit.py`.
MCP output now includes explicit server provenance and a do-not-follow boundary.
Provider-visible MCP tool descriptions and nested schema descriptions are framed as untrusted server-provided metadata.
OAuth bridge catalog output now includes a `trust_boundary`, framed server instructions, and framed tool descriptions/schemas.

### Delegate/Subagent Follow-Up

No clear low-priv to high-priv confusion confirmed in inspected paths.
`DelegateTools` preserves the original requester through `execution_identity`.
`SubAgentsTools.sessions_send()` and `sessions_spawn()` validate target agents against room availability for that requester and relay `ORIGINAL_SENDER_KEY`.
No delegate production changes made.

## Tests

Red tests first:

```bash
/tmp/codex-uv/bin/uv run pytest -n auto tests/test_memory_facade.py::TestMemoryFacade::test_format_memories_as_context tests/test_memory_file_backend.py::test_file_backend_build_memory_prompt_parts_splits_entrypoint_from_turn_context tests/test_memory_file_backend.py::test_file_backend_prompt_frames_matching_file_snippets_as_untrusted tests/test_mcp_results.py::test_tool_result_from_call_result_converts_text_images_and_resources tests/test_mcp_results.py::test_tool_result_from_call_result_raises_on_error tests/test_mcp_results.py::test_tool_result_from_call_result_summarizes_binary_embedded_resources tests/test_mcp_toolkit.py::test_mcp_toolkit_frames_tool_descriptions_as_untrusted_metadata tests/test_mcp_toolkit.py::test_oauth_mcp_toolkit_frames_catalog_payload_as_untrusted
```

Result: 8 failed before implementation.

Focused green tests:

```bash
/tmp/codex-uv/bin/uv run pytest -n auto tests/test_memory_facade.py::TestMemoryFacade::test_format_memories_as_context tests/test_memory_file_backend.py::test_file_backend_build_memory_prompt_parts_splits_entrypoint_from_turn_context tests/test_memory_file_backend.py::test_file_backend_prompt_frames_matching_file_snippets_as_untrusted tests/test_mcp_results.py::test_tool_result_from_call_result_converts_text_images_and_resources tests/test_mcp_results.py::test_tool_result_from_call_result_raises_on_error tests/test_mcp_results.py::test_tool_result_from_call_result_summarizes_binary_embedded_resources tests/test_mcp_toolkit.py::test_mcp_toolkit_frames_tool_descriptions_as_untrusted_metadata tests/test_mcp_toolkit.py::test_oauth_mcp_toolkit_frames_catalog_payload_as_untrusted
```

Result: 8 passed.
Coverage reporting emitted warnings from a stale `.coverage` DB, so broader verification used `--no-cov`.

Broader relevant subset:

```bash
/tmp/codex-uv/bin/uv run pytest -n auto --no-cov tests/test_memory_facade.py tests/test_memory_file_backend.py tests/test_mcp_results.py tests/test_mcp_toolkit.py tests/test_mcp_manager.py tests/test_delegate_tools.py tests/test_subagents.py
```

Result on isolated branch after review follow-up: 214 passed.

Review follow-up:

- malformed `memory` payload text now renders as empty data instead of crashing;
- metadata `line` type check now uses a normal `(int, str)` tuple;
- memory trust boundary is rendered at the `{memory_lines}` insertion point instead of after the first rendered newline;
- MCP schemas now get one schema-level trust-boundary description instead of recursively prefixing every nested field description.

Pre-commit:

```bash
/tmp/codex-uv/bin/uv run pre-commit run --all-files
```

Result: Python and repo hooks passed through `eslint`, then `typescript-check` and `check-bun-lock` failed because `bun` is not installed in this environment.
The exact blocker was `/run/current-system/sw/bin/bash: line 1: bun: command not found`.

## Residual Risk

MCP schemas are copied and framed once at schema level, so arbitrary nested schema strings can still contain untrusted text.
They are covered by the schema-level boundary, bridge-level `trust_boundary`, and function description boundary.

Full repository pytest was not run because task requested focused pytest.
