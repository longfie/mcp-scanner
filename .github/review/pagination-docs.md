## Paginated Server Lists

Tool and prompt scans follow MCP pagination for both remote and stdio servers.
Remote resource scans also follow pagination. This implementation supports the
MCP SDK 2.x dependency and protocol negotiation used by the scanner.

Bulk scans discover every listed item before analyzing the inventory. A scan
for a specific tool, prompt, or resource also finishes discovery before analysis
so a later duplicate cannot hide behind a benign first match. Duplicate names
for the requested tool or prompt, or duplicate URIs for the requested resource,
raise `mcpscanner.core.pagination.MCPPaginationError`. Named scans retain their
single-result API; they do not select an arbitrary duplicate. Bulk scans still
analyze all listed entries.

The scanner forwards opaque cursor values without changing them, including empty
strings, and continues past empty pages with a cursor. It reads SDK 2's
`next_cursor` attribute (with a legacy `nextCursor` fallback) and treats an
explicit `None` as the final page. Missing cursor fields are errors. Existing
prompt and resource content budgets apply across the combined inventory.

Discovery limits are configured through environment variables, set before
importing the scanner:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `MCP_SCANNER_MCP_LIST_PAGE_TIMEOUT_SECONDS` | `30` | Finite, positive timeout per list request |
| `MCP_SCANNER_MAX_MCP_LIST_PAGES` | `1000` | Positive maximum pages per list operation |
| `MCP_SCANNER_MAX_MCP_LIST_ITEMS` | `10000` | Positive maximum items per list operation |

The list timeout applies to **every page, including the first**. This adds a
scanner-level timeout to the original single-page request; it is intentional
and independent of `MCP_SCANNER_MCP_CONTENT_READ_TIMEOUT_SECONDS`, which controls
prompt/resource body reads. It is not a deadline for the whole scan. Named scans
now inspect subsequent pages and are subject to the same discovery limits.

Repeated cursors, missing/invalid cursor fields, exceeded limits, request
timeouts, and later-page request failures raise `MCPPaginationError`. First-page
MCP protocol errors retain their existing unsupported-capability handling;
other request errors are wrapped with their original cause. Cancellation
propagates unchanged, and named-scan iterators are explicitly closed.

These errors propagate from individual server scan methods instead of returning
a successful partial result. As connection/discovery errors, they map to HTTP
**502** in the REST API. Configuration scans retain their existing behavior of
recording a server error and continuing with the other servers.

