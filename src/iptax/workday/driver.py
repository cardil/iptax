"""Playwright implementation of browser driver protocols.

This module provides the production implementation of the browser driver
abstraction using Playwright's Page API.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal, cast

from iptax.workday.protocols import (
    KeyboardProtocol,
    LocatorProtocol,
    ResponseHandler,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.async_api import Locator, Page, Response


class PlaywrightLocator:
    """Wraps Playwright Locator to implement LocatorProtocol."""

    def __init__(self, locator: Locator) -> None:
        """Initialize PlaywrightLocator.

        Args:
            locator: Playwright Locator object to wrap
        """
        self._locator = locator

    async def wait_for(
        self,
        *,
        state: str = "visible",
        timeout: int | None = None,
    ) -> None:
        """Wait for element to reach specified state."""
        # Cast to expected literal type for Playwright API
        await self._locator.wait_for(
            state=cast(Literal["attached", "detached", "hidden", "visible"], state),
            timeout=timeout,
        )

    async def click(self) -> None:
        """Click the element."""
        await self._locator.click()

    async def fill(self, value: str) -> None:
        """Fill the element with text."""
        await self._locator.fill(value)

    async def text_content(self, *, timeout: int | None = None) -> str | None:
        """Get text content of element."""
        return await self._locator.text_content(timeout=timeout)

    def locator(self, selector: str) -> LocatorProtocol:
        """Get child locator by CSS selector."""
        return PlaywrightLocator(self._locator.locator(selector))

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,
        level: int | None = None,
    ) -> LocatorProtocol:
        """Get child element by ARIA role."""
        # Cast to Any to work with Playwright's strict role typing
        return PlaywrightLocator(
            self._locator.get_by_role(
                cast(Any, role), name=name, exact=exact, level=level
            )
        )


class PlaywrightKeyboard:
    """Wraps Playwright Keyboard to implement KeyboardProtocol."""

    def __init__(self, page: Page) -> None:
        """Initialize PlaywrightKeyboard.

        Args:
            page: Playwright Page object to access keyboard
        """
        self._page = page

    async def press(self, key: str) -> None:
        """Press a key or key combination."""
        await self._page.keyboard.press(key)

    async def type(self, text: str) -> None:
        """Type text character by character."""
        await self._page.keyboard.type(text)


class PlaywrightResponse:
    """Wraps Playwright Response to implement ResponseProtocol."""

    def __init__(self, response: Response) -> None:
        """Initialize PlaywrightResponse.

        Args:
            response: Playwright Response object to wrap
        """
        self._response = response

    @property
    def url(self) -> str:
        """Response URL."""
        return self._response.url

    @property
    def status(self) -> int:
        """HTTP status code."""
        return self._response.status

    @property
    def headers(self) -> dict[str, str]:
        """Response headers."""
        return self._response.headers

    # JSON parsing returns dynamic types from Playwright API (noqa:ANN401)
    async def json(self) -> Any:  # noqa: ANN401
        """Parse response body as JSON."""
        return await self._response.json()


class PlaywrightDriver:
    """Production implementation using real Playwright Page.

    This driver wraps a Playwright Page object and implements the
    BrowserDriverProtocol, allowing scraping functions to work with
    a real browser while remaining testable through the protocol.
    """

    def __init__(self, page: Page) -> None:
        """Initialize PlaywrightDriver.

        Args:
            page: Playwright Page object to wrap
        """
        self._page = page
        self._keyboard = PlaywrightKeyboard(page)
        # Track response handlers to maintain the mapping between
        # protocol handlers and wrapped Playwright handlers
        self._response_handlers: dict[ResponseHandler, Callable[[Response], object]] = (
            {}
        )

    @property
    def keyboard(self) -> KeyboardProtocol:
        """Access keyboard operations."""
        return self._keyboard

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,
        level: int | None = None,
    ) -> LocatorProtocol:
        """Get element by ARIA role."""
        # Cast to Any to work with Playwright's strict role typing
        return PlaywrightLocator(
            self._page.get_by_role(cast(Any, role), name=name, exact=exact, level=level)
        )

    def locator(self, selector: str) -> LocatorProtocol:
        """Get element by CSS selector."""
        return PlaywrightLocator(self._page.locator(selector))

    async def wait_for_timeout(self, timeout: int) -> None:
        """Wait for specified timeout in milliseconds."""
        await self._page.wait_for_timeout(timeout)

    async def wait_for_load_state(
        self,
        state: str = "domcontentloaded",
    ) -> None:
        """Wait for page to reach load state."""
        # Cast to expected literal type for Playwright API
        await self._page.wait_for_load_state(
            cast(Literal["domcontentloaded", "load", "networkidle"], state)
        )

    # JavaScript evaluation returns dynamic types from Playwright API (noqa:ANN401)
    async def evaluate(self, script: str) -> Any:  # noqa: ANN401
        """Evaluate JavaScript on the page."""
        return await self._page.evaluate(script)

    def on(self, event: str, handler: ResponseHandler) -> None:
        """Register response handler, wrapping Response objects.

        The handler receives ResponseProtocol instead of Playwright's Response,
        maintaining the abstraction.
        """

        async def wrapped_handler(response: Response) -> None:
            await handler(PlaywrightResponse(response))

        self._response_handlers[handler] = wrapped_handler
        # Cast event to Any to work with Playwright's strict event typing
        self._page.on(cast(Any, event), wrapped_handler)

    def remove_listener(self, event: str, handler: ResponseHandler) -> None:
        """Remove handler using the wrapped version."""
        if handler in self._response_handlers:
            wrapped = self._response_handlers.pop(handler)
            self._page.remove_listener(event, wrapped)
