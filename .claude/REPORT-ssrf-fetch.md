# SSRF and Local-File Fetch Report

## Scope

Validated and fixed:

- TOOLS-TOOLS-1 browser open/navigate arbitrary URL.
- TOOLS-TOOLS-2 browser upload arbitrary local paths.
- TOOLS-TOOLS-5 custom_api and crawl4ai missing server-fetch validation.
- MCP-MCP-3 remote MCP transport missing URL validation.
- MCP OAuth discovery had a separate weaker host validator.

Checked:

- Website reader already used `server_fetch_url`, redirect-hop validation, and DNS-rebind connect-time validation.
- EGRESS-EGRESS-4 was not separately changed because this patch did not touch a local website proxy path beyond shared helper users.

## Findings

TOOLS-TOOLS-1 was real.
`BrowserTools.browser(action="open"|"navigate")` sent `targetUrl` directly to Playwright, allowing `file://`, loopback, private, link-local, and metadata URLs.

TOOLS-TOOLS-2 was real.
`BrowserTools._upload` expanded user paths and passed them directly to Playwright, allowing arbitrary host file upload.

TOOLS-TOOLS-5 was real.
`custom_api_tools()` returned Agno `CustomApiTools` directly, and `crawl4ai_tools()` returned Agno `Crawl4aiTools` directly.
Both accepted agent-provided URLs without MindRoom server-fetch validation.

MCP-MCP-3 was real.
Remote SSE and streamable HTTP MCP URLs were handed to MCP clients without `server_fetch_url` validation.

MCP OAuth discovery also had a real related gap.
It duplicated URL safety checks and could allow metadata hostnames when DNS did not resolve locally.

## Fix

- Browser open/navigate now validates target URLs with `validate_server_fetch_url`.
- Browser contexts install a Playwright route guard that aborts unsafe HTTP requests before network fetch.
- Browser uploads now resolve paths and only allow files under MindRoom runtime storage, browser output storage, or active tool-context storage.
- Custom API now returns a MindRoom wrapper class that validates the combined base URL and endpoint, disables automatic redirects, validates every redirect target, then preserves the Agno response shape.
- Crawl4AI now returns a MindRoom wrapper class that validates each URL before crawling.
- MCP remote transports now validate configured URLs before opening clients.
- MCP OAuth discovery now reuses `validate_server_fetch_url`, preserving existing env toggles for insecure/private discovery while keeping metadata/link-local protections.

## Tests

Red tests first reproduced unsafe behavior:

```bash
/Users/bas.nijholt/Library/Python/3.9/bin/uv run --python /opt/homebrew/bin/python3.13 pytest tests/test_server_fetch_url_validation.py::test_custom_api_tool_rejects_private_endpoint_before_request tests/test_server_fetch_url_validation.py::test_custom_api_tool_validates_combined_base_url tests/test_server_fetch_url_validation.py::test_crawl4ai_tool_rejects_private_url_before_crawling tests/test_browser_tool.py::test_browser_open_rejects_private_target_url tests/test_browser_tool.py::test_browser_navigate_rejects_file_target_url tests/test_browser_tool.py::test_browser_upload_paths_must_stay_under_runtime_storage tests/test_mcp_transports.py::test_open_remote_transport_rejects_private_url_before_client_call -n 0 --no-cov -q
```

Final focused validation:

```bash
/Users/bas.nijholt/Library/Python/3.9/bin/uv run --python /opt/homebrew/bin/python3.13 pytest tests/test_server_fetch_url_validation.py tests/test_browser_tool.py tests/test_mcp_transports.py tests/test_mcp_oauth.py tests/test_website_tool.py -n 0 --no-cov -q
```

Result: 117 passed.

Lint:

```bash
/Users/bas.nijholt/Library/Python/3.9/bin/uv run --python /opt/homebrew/bin/python3.13 ruff check src/mindroom/custom_tools/browser.py src/mindroom/tools/custom_api.py src/mindroom/tools/crawl4ai.py src/mindroom/mcp/transports.py src/mindroom/mcp/oauth.py tests/test_server_fetch_url_validation.py tests/test_browser_tool.py tests/test_mcp_transports.py tests/test_mcp_oauth.py
```

Result: all checks passed.

## Notes

The default `pytest` invocation enabled xdist and coverage.
That run hit a coverage sqlite internal error unrelated to these changes, so focused verification used `-n 0 --no-cov`.
