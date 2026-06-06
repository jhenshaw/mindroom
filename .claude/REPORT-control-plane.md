# Control Plane Safety Report

Branch: `security/control-plane-boundary-4`.
Base: `origin/main` at `952ae960e`, including PR #1176 where `!config` is disabled by default and PR #1177 where SaaS auth privilege leaks were fixed.

## Scope

Hardened chat config commands, config validation, API config writes, skills writes, plugin validation, knowledge paths, model/plugin/MCP safety, and MCP remote transports.
Kept #1176 behavior intact: `!config` stays disabled by default and still requires a global admin when enabled.
Did not include SaaS, memory, or unrelated MCP result/toolkit changes from other worker branches.

## Fixes

Chat config commands now reject privileged paths such as `authorization`, `models`, `plugins`, `knowledge_bases`, `mcp_servers`, `prompts`, `worker_egress_brokers`, `debug`, `llm_request_log_dir`, and `memory.embedder`.
Chat config commands also reject parent paths that would expose restricted child blocks.
Chat config output now redacts sensitive values before echoing YAML into Matrix.
Chat config set previews now redact sensitive old and new values before confirmation.
Chat config preview/apply validation no longer imports or executes plugin modules.
API config and skills writes now fail closed when no dashboard auth is configured, unless `MINDROOM_UNSAFE_ALLOW_UNAUTHENTICATED_CONTROL_PLANE_WRITES=true` is explicitly set.
API config save/raw validation also avoids plugin module execution.
Local plugin paths are confined to the runtime config directory or storage root, while explicit Python package plugin specs remain allowed.
Plugin manifest-relative module and skill paths are confined under the validated plugin root.
Knowledge base paths and stdio MCP `cwd` or path-like commands are confined to the runtime config directory or storage root.
Remote MCP transports validate URLs with server-fetch SSRF rules before opening SSE or streamable HTTP clients.
Remote MCP URLs are also rejected during config validation so unsafe URLs do not persist to disk.
Plugin no-exec validation parses literal tool metadata without marking skipped execution as a plugin load failure.

## Verification

Compiled touched modules and focused tests with `PYTHONPATH=$PWD/src` because the available venv points at another worktree.
Focused review-regression command passed with `6 passed`.
Focused original-regression command passed with `14 passed`.
Touched-suite command passed with `391 passed, 4 warnings`.
Warnings were existing Starlette `TestClient` cookie deprecations.
Ruff check passed on touched files.
Tach check passed with `python -m tach check --dependencies --interfaces`.
Pre-commit passed `trim trailing whitespace`, `fix end of files`, `check docstring is first`, `check yaml`, `ruff check`, `ruff format`, `pyproject-fmt`, `prettier`, `eslint`, `check json`, and `pretty format json`.
Pre-commit could not complete because `uv`, `bun`, `.venv/bin/ty`, `.venv/bin/python`, and `.venv/bin/markdown-code-runner` are missing in this clean checkout environment.
