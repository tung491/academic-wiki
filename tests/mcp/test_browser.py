import pytest
from academic_wiki_mcp.browser import (
    Element, BrowserBackend, PlaywrightBackend, SeleniumBackend,
    get_backend, detect_blocked,
)


def test_element_is_abstract():
    with pytest.raises(TypeError):
        Element()


def test_browser_backend_is_abstract():
    with pytest.raises(TypeError):
        BrowserBackend()


def test_get_backend_playwright():
    backend = get_backend("playwright")
    assert isinstance(backend, PlaywrightBackend)


def test_get_backend_selenium():
    backend = get_backend("selenium")
    assert isinstance(backend, SeleniumBackend)


def test_get_backend_invalid():
    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend("firefox")


def test_detect_blocked_short_body():
    assert detect_blocked("<html><body>short</body></html>") is True


def test_detect_blocked_captcha():
    html = '<div id="cf-challenge-running">Checking your browser</div>' + "x" * 2000
    assert detect_blocked(html) is True


def test_detect_blocked_normal():
    html = "<html><body>" + "Normal content. " * 200 + "</body></html>"
    assert detect_blocked(html) is False
