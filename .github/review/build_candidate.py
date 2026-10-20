"""Build a review candidate without modifying the live PR branch."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

OLD = "e1c55260a4079c6fd07a1075a41db6ac5a32606a"
BASE = "10032f9886dfc6850c2ab673626b61d6e0340a34"
source = Path(sys.argv[1]).resolve()
payload = Path(__file__).resolve().parent


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(source), *args], check=check,
                          capture_output=True, text=True)


def replace_once(path, old, new, count=1):
    file = source / path
    text = file.read_text()
    assert text.count(old) == count, (path, old[:80], text.count(old))
    file.write_text(text.replace(old, new))


assert git("rev-parse", "HEAD").stdout.strip() == OLD
git("config", "user.name", "Ankang")
git("config", "user.email", "tfyt@vip.qq.com")
result = git("merge", "--no-commit", "--no-ff", BASE, check=False)
print(result.stdout)
assert result.returncode == 1
conflicts = set(git("diff", "--name-only", "--diff-filter=U").stdout.splitlines())
assert conflicts == {"mcpscanner/core/scanner.py", "pyproject.toml", "uv.lock"}, conflicts
git("checkout", "--theirs", "--", "pyproject.toml", "uv.lock")
file = source / "mcpscanner/core/scanner.py"
text = file.read_text()
pattern = (
    r"<<<<<<< HEAD\n            for resource in resources:\n=======\n"
    r"            for resource in resource_list.resources:\n"
    r"                resource_mime = self\._advertised_resource_mime\(resource\)\n"
    r">>>>>>> [^\n]+\n"
)
text, count = re.subn(pattern,
    "            for resource in resources:\n"
    "                resource_mime = self._advertised_resource_mime(resource)\n", text)
assert count == 1
file.write_text(text)
git("add", "mcpscanner/core/scanner.py", "pyproject.toml", "uv.lock")
assert git("write-tree").stdout.strip() == "03c3f706eb1b52aade3372a2393da290ad59b826"

for name, target in {
    "pagination.py": "mcpscanner/core/pagination.py",
    "test_pagination_review.py": "tests/test_pagination_review.py",
    "stdio_paginated_server.py": "tests/fixtures/stdio_paginated_server.py",
}.items():
    shutil.copyfile(payload / name, source / target)

replace_once("mcpscanner/config/constants.py", "    # AWS Configuration Defaults\n", '''    # Inventory discovery has its own limits, independent of content reads.
    MCP_LIST_PAGE_TIMEOUT_SECONDS: float = float(
        os.getenv("MCP_SCANNER_MCP_LIST_PAGE_TIMEOUT_SECONDS", "30")
    )
    MAX_MCP_LIST_PAGES: int = int(
        os.getenv("MCP_SCANNER_MAX_MCP_LIST_PAGES", "1000")
    )
    MAX_MCP_LIST_ITEMS: int = int(
        os.getenv("MCP_SCANNER_MAX_MCP_LIST_ITEMS", "10000")
    )

    # AWS Configuration Defaults
''')
replace_once("mcpscanner/core/scanner.py",
             "from .pagination import iter_mcp_items",
             "from .pagination import find_mcp_item, iter_mcp_items")
for entity in ("tool", "prompt"):
    old = f'''                async for {entity} in iter_mcp_items(session.list_{entity}s, "{entity}s"):
                    if {entity}.name == {entity}_name:
                        target_{entity} = {entity}
                        break'''
    new = f'''                target_{entity} = await find_mcp_item(
                    session.list_{entity}s, "{entity}s", "name", {entity}_name
                )'''
    replace_once("mcpscanner/core/scanner.py", old, new, count=2)
replace_once("mcpscanner/core/scanner.py", '''                async for resource in iter_mcp_items(
                    session.list_resources, "resources"
                ):
                    # Convert AnyUrl to string for comparison.
                    if str(resource.uri) == resource_uri:
                        target_resource = resource
                        break''', '''                target_resource = await find_mcp_item(
                    session.list_resources, "resources", "uri", resource_uri
                )''')

for path in ("tests/test_pagination.py", "tests/test_scanner_pagination.py"):
    file = source / path
    text = file.read_text()
    text = text.replace("from mcp.shared.exceptions import McpError",
                        "from mcp.shared.exceptions import MCPError as McpError")
    text = text.replace("ErrorData, ", "").replace("    ErrorData,\n", "")
    text = text.replace("inputSchema=", "input_schema=").replace("mimeType=", "mime_type=")
    text = text.replace("nextCursor", "next_cursor")
    text = text.replace("MCP_CONTENT_READ_TIMEOUT_SECONDS", "MCP_LIST_PAGE_TIMEOUT_SECONDS")
    text = text.replace('McpError(ErrorData(code=-32601, message="Method not found"))',
                        'McpError(-32601, "Method not found")')
    text = text.replace("McpError(ErrorData(code=code, message=message))", "McpError(code, message)")
    file.write_text(text)
replace_once("tests/test_scanner_pagination.py",
    "async def test_single_scan_stops_when_target_is_found(",
    "async def test_single_scan_finishes_discovery_before_analysis(")
replace_once("tests/test_scanner_pagination.py", '''    # This cursor is cyclic on page two, but irrelevant once the target is found.
    pages.append(listing(collection, [listed_item(collection, "later")], "next"))
    pages.append(AssertionError("A named scan must not request unrelated pages"))''', '''    # Later pages must be checked even after finding the requested identity.
    pages.append(listing(collection, [listed_item(collection, "later")], "last"))
    pages.append(listing(collection, [listed_item(collection, "unrelated")]))''')
replace_once("tests/test_scanner_pagination.py",
    "assert len(session.list_requests) == target_page",
    "assert len(session.list_requests) == target_page + 1")

file = source / "docs/programmatic-usage.md"
text = file.read_text()
a = text.index("## Paginated Server Lists")
b = text.index("## Advanced Examples", a)
file.write_text(text[:a] + (payload / "pagination-docs.md").read_text() + text[b:])

paths = [
    "docs/programmatic-usage.md", "mcpscanner/config/constants.py",
    "mcpscanner/core/pagination.py", "mcpscanner/core/scanner.py",
    "tests/test_pagination.py", "tests/test_scanner_pagination.py",
    "tests/test_pagination_review.py", "tests/fixtures/stdio_paginated_server.py",
]
git("add", *paths)
assert set(git("diff", "--cached", "--name-only", BASE).stdout.splitlines()) == set(paths)
git("diff", "--cached", "--check")
for path in ("pyproject.toml", "uv.lock"):
    assert (source / path).read_bytes() == subprocess.check_output(
        ["git", "-C", str(source), "show", f"{BASE}:{path}"])
print(git("diff", "--cached", "--stat", BASE).stdout)
print("Candidate constructed; no PR ref has been updated.")
