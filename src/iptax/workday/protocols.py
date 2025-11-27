"""Browser driver protocols for Workday scraping abstraction.

This module defines Protocol interfaces that allow the scraping module to work
with different browser implementations (Playwright for production, fakes for testing).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LocatorProtocol(Protocol):
    """Protocol for element locator operations.

    Abstracts Playwright's Locator interface to enable testing without a browser.
    """

    async def wait_for(
        self,
        *,
        state: str = "visible",
        timeout: int | None = None,
    ) -> None:
        """Wait for element to reach specified state.

        Args:
            state: Target state - "visible", "hidden", "attached", "detached"
            timeout: Maximum wait time in milliseconds
        """
        ...

    async def click(self) -> None:
        """Click the element."""
        ...

    async def fill(self, value: str) -> None:
        """Fill the element with text (clears existing content)."""
        ...

    async def text_content(self, *, timeout: int | None = None) -> str | None:
        """Get text content of element.

        Args:
            timeout: Maximum wait time in milliseconds

        Returns:
            Text content or None if element has no text
        """
        ...

    def locator(self, selector: str) -> LocatorProtocol:
        """Get child locator by CSS selector.

        Args:
            selector: CSS selector string

        Returns:
            Child locator
        """
        ...

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,
        level: int | None = None,
    ) -> LocatorProtocol:
        """Get child element by ARIA role.

        Args:
            role: ARIA role (e.g., "button", "heading", "textbox")
            name: Accessible name or pattern to match
            exact: Whether name must match exactly
            level: Heading level (for role="heading")

        Returns:
            Child locator matching the role
        """
        ...


@runtime_checkable
class KeyboardProtocol(Protocol):
    """Protocol for keyboard operations."""

    async def press(self, key: str) -> None:
        """Press a key or key combination.

        Args:
            key: Key name (e.g., 'Enter') or combination (e.g., 'Control+a')
        """
        ...

    async def type(self, text: str) -> None:
        """Type text character by character.

        Args:
            text: Text to type
        """
        ...


@runtime_checkable
class ResponseProtocol(Protocol):
    """Protocol for HTTP response objects.

    Used for intercepting and handling network responses.
    """

    @property
    def url(self) -> str:
        """Response URL."""
        ...

    @property
    def status(self) -> int:
        """HTTP status code."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Response headers."""
        ...

    # JSON parsing returns dynamic types from Playwright API (noqa:ANN401)
    async def json(self) -> Any:  # noqa: ANN401
        """Parse response body as JSON.

        Returns:
            Parsed JSON data
        """
        ...


# Type alias for response event handlers
ResponseHandler = Callable[[ResponseProtocol], Coroutine[Any, Any, None]]


@runtime_checkable
class BrowserDriverProtocol(Protocol):
    """Protocol for browser page operations used in Workday scraping.

    This abstraction allows unit testing without real browser automation.
    Implementations:
    - PlaywrightDriver: Wraps real Playwright Page for production
    - FakeBrowserDriver: Configurable fake for unit testing
    """

    @property
    def keyboard(self) -> KeyboardProtocol:
        """Access keyboard operations.

        Returns:
            Keyboard protocol implementation
        """
        ...

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,
        level: int | None = None,
    ) -> LocatorProtocol:
        """Get element by ARIA role.

        Args:
            role: ARIA role (e.g., "button", "heading", "textbox")
            name: Accessible name or pattern to match
            exact: Whether name must match exactly
            level: Heading level (for role="heading")

        Returns:
            Locator for the element
        """
        ...

    def locator(self, selector: str) -> LocatorProtocol:
        """Get element by CSS selector.

        Args:
            selector: CSS selector string

        Returns:
            Locator for the element
        """
        ...

    async def wait_for_timeout(self, timeout: int) -> None:
        """Wait for specified timeout.

        Args:
            timeout: Wait time in milliseconds
        """
        ...

    async def wait_for_load_state(
        self,
        state: str = "domcontentloaded",
    ) -> None:
        """Wait for page to reach load state.

        Args:
            state: Load state to wait for (domcontentloaded, load, networkidle)
        """
        ...

    # JavaScript evaluation returns dynamic types from Playwright API (noqa:ANN401)
    async def evaluate(self, script: str) -> Any:  # noqa: ANN401
        """Evaluate JavaScript on the page.

        Args:
            script: JavaScript code to execute

        Returns:
            Result of the JavaScript evaluation
        """
        ...

    def on(self, event: str, handler: ResponseHandler) -> None:
        """Register event handler.

        Args:
            event: Event name (e.g., 'response')
            handler: Async function to handle the event
        """
        ...

    def remove_listener(self, event: str, handler: ResponseHandler) -> None:
        """Remove previously registered event handler.

        Args:
            event: Event name (e.g., 'response')
            handler: Handler function to remove
        """
        ...
