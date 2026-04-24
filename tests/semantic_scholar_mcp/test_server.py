import pytest


@pytest.mark.asyncio
async def test_server_imports_register_three_tools():
    # Import the server module for its side effect: registering tools on the
    # FastMCP instance via the @mcp.tool() decorators in tools.discovery.
    import semantic_scholar_mcp.server  # noqa: F401
    from semantic_scholar_mcp import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert names == {
        "semantic_scholar_search",
        "get_paper_by_doi",
        "discover_related",
    }


def test_server_has_main_entry_point():
    from semantic_scholar_mcp.server import main
    assert callable(main)
