from __future__ import annotations
import asyncio
import re
from abc import ABC, abstractmethod
from typing import Any


class Element(ABC):
    @abstractmethod
    async def text(self) -> str: ...
    @abstractmethod
    async def attribute(self, name: str) -> str | None: ...
    @abstractmethod
    async def scroll_into_view(self) -> None: ...
    @abstractmethod
    async def click(self) -> None: ...
    @abstractmethod
    async def children(self) -> list[Element]: ...
    @abstractmethod
    async def next_sibling(self) -> Element | None: ...
    @abstractmethod
    async def parent(self) -> Element | None: ...
    @abstractmethod
    async def tag_name(self) -> str: ...


class BrowserBackend(ABC):
    @abstractmethod
    async def navigate(self, url: str) -> None: ...
    @abstractmethod
    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None: ...
    @abstractmethod
    async def query_selector(self, selector: str) -> Element | None: ...
    @abstractmethod
    async def query_selector_all(self, selector: str) -> list[Element]: ...
    @abstractmethod
    async def evaluate(self, js: str, *args: Any) -> Any: ...
    @abstractmethod
    async def download_image(self, url: str) -> bytes: ...
    @abstractmethod
    async def get_page_content(self) -> str: ...
    @abstractmethod
    async def sleep(self, ms: int) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...


_CAPTCHA_PATTERNS = [
    re.compile(r'id="cf-challenge', re.IGNORECASE),
    re.compile(r'class="g-recaptcha"', re.IGNORECASE),
    re.compile(r'<iframe[^>]*recaptcha', re.IGNORECASE),
]


def detect_blocked(html: str) -> bool:
    if len(html) < 1024:
        return True
    for pat in _CAPTCHA_PATTERNS:
        if pat.search(html):
            return True
    return False


# --- Playwright Backend ---

class PlaywrightElement(Element):
    def __init__(self, handle):
        self._h = handle

    async def text(self) -> str:
        return (await self._h.text_content()) or ""

    async def attribute(self, name: str) -> str | None:
        return await self._h.get_attribute(name)

    async def scroll_into_view(self) -> None:
        await self._h.scroll_into_view_if_needed()

    async def click(self) -> None:
        await self._h.click()

    async def children(self) -> list[Element]:
        handles = await self._h.query_selector_all(":scope > *")
        return [PlaywrightElement(h) for h in handles]

    async def next_sibling(self) -> Element | None:
        sib = await self._h.evaluate_handle(
            "el => el.nextElementSibling"
        )
        if await sib.evaluate("el => el === null"):
            return None
        return PlaywrightElement(sib.as_element())

    async def parent(self) -> Element | None:
        p = await self._h.evaluate_handle("el => el.parentElement")
        if await p.evaluate("el => el === null"):
            return None
        return PlaywrightElement(p.as_element())

    async def tag_name(self) -> str:
        return (await self._h.evaluate("el => el.tagName")).upper()


class PlaywrightBackend(BrowserBackend):
    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None

    async def _ensure_browser(self):
        if self._page is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()

    async def navigate(self, url: str) -> None:
        await self._ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None:
        await self._page.wait_for_selector(selector, timeout=timeout)

    async def query_selector(self, selector: str) -> Element | None:
        h = await self._page.query_selector(selector)
        return PlaywrightElement(h) if h else None

    async def query_selector_all(self, selector: str) -> list[Element]:
        handles = await self._page.query_selector_all(selector)
        return [PlaywrightElement(h) for h in handles]

    async def evaluate(self, js: str, *args: Any) -> Any:
        unwrapped = tuple(
            a._h if isinstance(a, PlaywrightElement) else a for a in args
        )
        return await self._page.evaluate(js, *unwrapped)

    async def download_image(self, url: str) -> bytes:
        resp = await self._page.context.request.get(url)
        return await resp.body()

    async def get_page_content(self) -> str:
        return await self._page.content()

    async def sleep(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000)

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._page = None
        self._browser = None
        self._pw = None


# --- Selenium Backend ---

class SeleniumElement(Element):
    def __init__(self, el, driver):
        self._el = el
        self._driver = driver

    async def text(self) -> str:
        return self._el.text

    async def attribute(self, name: str) -> str | None:
        return self._el.get_attribute(name)

    async def scroll_into_view(self) -> None:
        self._driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'instant',block:'center'})", self._el
        )

    async def click(self) -> None:
        self._el.click()

    async def children(self) -> list[Element]:
        kids = self._el.find_elements("css selector", ":scope > *")
        return [SeleniumElement(k, self._driver) for k in kids]

    async def next_sibling(self) -> Element | None:
        sib = self._driver.execute_script(
            "return arguments[0].nextElementSibling", self._el
        )
        return SeleniumElement(sib, self._driver) if sib else None

    async def parent(self) -> Element | None:
        p = self._driver.execute_script(
            "return arguments[0].parentElement", self._el
        )
        return SeleniumElement(p, self._driver) if p else None

    async def tag_name(self) -> str:
        return self._el.tag_name.upper()


class SeleniumBackend(BrowserBackend):
    def __init__(self):
        self._driver = None

    def _ensure_driver(self):
        if self._driver is None:
            import undetected_chromedriver as uc
            from selenium_stealth import stealth
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            self._driver = uc.Chrome(options=options)
            stealth(self._driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True)

    async def navigate(self, url: str) -> None:
        self._ensure_driver()
        self._driver.get(url)

    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        WebDriverWait(self._driver, timeout / 1000).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    async def query_selector(self, selector: str) -> Element | None:
        from selenium.webdriver.common.by import By
        els = self._driver.find_elements(By.CSS_SELECTOR, selector)
        return SeleniumElement(els[0], self._driver) if els else None

    async def query_selector_all(self, selector: str) -> list[Element]:
        from selenium.webdriver.common.by import By
        els = self._driver.find_elements(By.CSS_SELECTOR, selector)
        return [SeleniumElement(e, self._driver) for e in els]

    async def evaluate(self, js: str, *args: Any) -> Any:
        unwrapped = tuple(
            a._el if isinstance(a, SeleniumElement) else a for a in args
        )
        return self._driver.execute_script(js, *unwrapped)

    async def download_image(self, url: str) -> bytes:
        import requests
        cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
        resp = requests.get(url, cookies=cookies, timeout=30)
        resp.raise_for_status()
        return resp.content

    async def get_page_content(self) -> str:
        return self._driver.page_source

    async def sleep(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000)

    async def close(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None


_backend_override: dict[str, str] = {}


def get_backend(name: str) -> BrowserBackend:
    if name == "playwright":
        return PlaywrightBackend()
    elif name == "selenium":
        return SeleniumBackend()
    raise ValueError(f"Unknown backend: {name}")


def get_backend_for_publisher(publisher_domain: str, default: str = "playwright", fallback: str = "selenium") -> tuple[BrowserBackend, str]:
    """Returns (backend, backend_name). Uses session-learned overrides if a previous fallback succeeded."""
    name = _backend_override.get(publisher_domain, default)
    return get_backend(name), name


def record_backend_success(publisher_domain: str, backend_name: str) -> None:
    """Record that a backend worked for a publisher, so future calls skip the failing one."""
    _backend_override[publisher_domain] = backend_name
