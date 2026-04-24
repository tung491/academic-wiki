def test_package_exports_fastmcp_instance():
    from semantic_scholar_mcp import mcp

    assert mcp is not None
    assert mcp.name == "SemanticScholarServer"


def test_config_exposes_api_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key-123")
    import importlib
    from semantic_scholar_mcp import config
    importlib.reload(config)
    assert config.SEMANTIC_SCHOLAR_API_KEY == "test-key-123"


def test_config_defaults_to_empty_string(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    import importlib
    from semantic_scholar_mcp import config
    importlib.reload(config)
    assert config.SEMANTIC_SCHOLAR_API_KEY == ""
