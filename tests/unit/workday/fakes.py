"""Fake browser driver implementations for testing.

This module provides configurable fake implementations of the browser driver
protocols, allowing unit tests to run without real browser automation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from iptax.workday.protocols import (
    LocatorProtocol,
    ResponseHandler,
)


@dataclass
class FakeLocator:
    """Configurable fake locator for testing.

    Example:
        locator = FakeLocator(text_content_value="Hello")
        assert await locator.text_content() == "Hello"
    """

    text_content_value: str | None = None
    text_content_sequence: list[str] = field(default_factory=list)
    _sequence_index: int = field(default=0, init=False, repr=False)
    wait_for_raises: Exception | None = None
    click_callback: Callable[[], None] | None = None
    fill_callback: Callable[[str], None] | None = None
    child_locators: dict[str, FakeLocator] = field(default_factory=dict)

    async def wait_for(
        self,
        *,
        state: str = "visible",  # noqa: ARG002 - matches Playwright
        timeout: int | None = None,  # noqa: ARG002 - matches Playwright
    ) -> None:
        """Wait for element - raises if configured to do so.

        Args match Playwright interface but are unused in fake.
        """
        if self.wait_for_raises:
            raise self.wait_for_raises

    async def click(self) -> None:
        """Click the element - calls callback if configured."""
        if self.click_callback:
            self.click_callback()

    async def fill(self, value: str) -> None:
        """Fill the element - calls callback if configured."""
        if self.fill_callback:
            self.fill_callback(value)

    # Timeout matches Playwright interface (noqa:ARG002)
    async def text_content(
        self, *, timeout: int | None = None  # noqa: ARG002
    ) -> str | None:
        """Get text content.

        Returns values from sequence if configured, otherwise returns single value.
        Timeout arg matches Playwright interface but is unused in fake.
        """
        if self.text_content_sequence:
            if self._sequence_index < len(self.text_content_sequence):
                result = self.text_content_sequence[self._sequence_index]
                self._sequence_index += 1
                return result
            return self.text_content_sequence[-1]
        return self.text_content_value

    def locator(self, selector: str) -> FakeLocator:
        """Get child locator by CSS selector."""
        return self.child_locators.get(selector, FakeLocator())

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,  # noqa: ARG002 - matches Playwright
        level: int | None = None,
    ) -> FakeLocator:
        """Get child element by ARIA role.

        Args match Playwright interface; exact is unused in fake.
        """
        # Build key from role, name, and level for lookup (matches _make_role_key)
        name_str = name.pattern if isinstance(name, re.Pattern) else str(name)
        key = f"{role}:{name_str}:{level}"
        return self.child_locators.get(key, FakeLocator())


@dataclass
class FakeKeyboard:
    """Fake keyboard for testing.

    Tracks all key presses and typed text for assertions in tests.
    """

    pressed_keys: list[str] = field(default_factory=list)
    typed_text: list[str] = field(default_factory=list)

    async def press(self, key: str) -> None:
        """Press a key - records in pressed_keys list."""
        self.pressed_keys.append(key)

    async def type(self, text: str) -> None:
        """Type text - records in typed_text list."""
        self.typed_text.append(text)


@dataclass
class FakeResponse:
    """Fake HTTP response for testing.

    Example:
        response = FakeResponse(
            url="https://example.com/api",
            status=200,
            headers={"content-type": "application/json"},
            json_data={"result": "success"},
        )
    """

    url: str = ""
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    json_data: Any = None

    # JSON parsing returns dynamic types (noqa:ANN401)
    async def json(self) -> Any:  # noqa: ANN401
        """Return the configured JSON data."""
        return self.json_data


@dataclass
class FakeBrowserDriver:
    """Configurable fake browser driver for testing.

    This fake allows tests to configure expected responses and verify
    interactions without requiring a real browser.

    Example:
        driver = FakeBrowserDriver()
        driver.configure_locator(
            role="heading",
            name=re.compile(r"\\w+ \\d+.*\\d{4}"),
            level=2,
            text_content="Nov 24 - 30, 2025",
        )

        result = await get_week_heading_text(driver)
        assert result == "Nov 24 - 30, 2025"
    """

    keyboard: FakeKeyboard = field(default_factory=FakeKeyboard)
    locators: dict[str, FakeLocator] = field(default_factory=dict)
    css_locators: dict[str, FakeLocator] = field(default_factory=dict)
    response_handlers: list[ResponseHandler] = field(default_factory=list)
    pending_responses: list[FakeResponse] = field(default_factory=list)
    evaluate_results: dict[str, Any] = field(default_factory=dict)

    # Many parameters needed to configure all locator behavior (noqa:PLR0913)
    def configure_locator(  # noqa: PLR0913
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        level: int | None = None,
        text_content: str | None = None,
        text_content_sequence: list[str] | None = None,
        wait_for_raises: Exception | None = None,
        click_callback: Callable[[], None] | None = None,
        fill_callback: Callable[[str], None] | None = None,
    ) -> FakeLocator:
        """Configure a locator response for get_by_role calls.

        Args:
            role: ARIA role to match
            name: Name pattern to match (optional)
            level: Heading level (optional, for role="heading")
            text_content: Single text content value to return
            text_content_sequence: Sequence of values for multiple calls
            wait_for_raises: Exception to raise on wait_for()
            click_callback: Callback to invoke on click()
            fill_callback: Callback to invoke on fill()

        Returns:
            The configured FakeLocator for further customization
        """
        key = self._make_role_key(role, name, level)
        locator = FakeLocator(
            text_content_value=text_content,
            text_content_sequence=text_content_sequence or [],
            wait_for_raises=wait_for_raises,
            click_callback=click_callback,
            fill_callback=fill_callback,
        )
        self.locators[key] = locator
        return locator

    def configure_css_locator(
        self,
        selector: str,
        *,
        text_content: str | None = None,
        wait_for_raises: Exception | None = None,
        child_locators: dict[str, FakeLocator] | None = None,
    ) -> FakeLocator:
        """Configure a locator response for CSS selector calls.

        Args:
            selector: CSS selector string
            text_content: Text content to return
            wait_for_raises: Exception to raise on wait_for()
            child_locators: Child locators for nested elements

        Returns:
            The configured FakeLocator for further customization
        """
        locator = FakeLocator(
            text_content_value=text_content,
            wait_for_raises=wait_for_raises,
            child_locators=child_locators or {},
        )
        self.css_locators[selector] = locator
        return locator

    def queue_response(self, response: FakeResponse) -> None:
        """Queue a response to be delivered to handlers.

        Call trigger_responses() to actually deliver the responses.

        Args:
            response: FakeResponse to queue
        """
        self.pending_responses.append(response)

    async def trigger_responses(self) -> None:
        """Trigger all pending responses to registered handlers.

        This simulates network responses being received.
        """
        for response in self.pending_responses:
            for handler in self.response_handlers:
                await handler(response)
        self.pending_responses.clear()

    def get_by_role(
        self,
        role: str,
        *,
        name: str | re.Pattern[str] | None = None,
        exact: bool = False,  # noqa: ARG002 - matches Playwright
        level: int | None = None,
    ) -> LocatorProtocol:
        """Get element by ARIA role.

        Args match Playwright interface; exact is unused in fake.
        """
        key = self._make_role_key(role, name, level)
        return self.locators.get(key, FakeLocator())

    def locator(self, selector: str) -> LocatorProtocol:
        """Get element by CSS selector."""
        return self.css_locators.get(selector, FakeLocator())

    async def wait_for_timeout(self, timeout: int) -> None:
        """Wait for timeout - no-op in tests."""
        pass

    async def wait_for_load_state(
        self,
        state: str = "domcontentloaded",
    ) -> None:
        """Wait for load state - no-op in tests."""
        pass

    # JavaScript evaluation returns dynamic types (noqa:ANN401)
    async def evaluate(self, script: str) -> Any:  # noqa: ANN401
        """Evaluate JavaScript - returns configured result if any."""
        return self.evaluate_results.get(script)

    def on(self, event: str, handler: ResponseHandler) -> None:
        """Register event handler."""
        if event == "response":
            self.response_handlers.append(handler)

    def remove_listener(self, event: str, handler: ResponseHandler) -> None:
        """Remove event handler."""
        if event == "response" and handler in self.response_handlers:
            self.response_handlers.remove(handler)

    @staticmethod
    def _make_role_key(
        role: str,
        name: str | re.Pattern[str] | None,
        level: int | None,
    ) -> str:
        """Create lookup key from role parameters.

        Args:
            role: ARIA role
            name: Name or pattern
            level: Heading level

        Returns:
            String key for locator lookup
        """
        name_str = name.pattern if isinstance(name, re.Pattern) else str(name)
        return f"{role}:{name_str}:{level}"
