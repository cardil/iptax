"""Tests for workday.driver module."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from iptax.workday.driver import (
    PlaywrightDriver,
    PlaywrightKeyboard,
    PlaywrightLocator,
    PlaywrightResponse,
)


class TestPlaywrightLocator:
    """Test PlaywrightLocator wrapper."""

    @pytest.mark.asyncio
    async def test_wait_for(self) -> None:
        """Test wait_for delegates to Playwright locator."""
        mock_locator = AsyncMock()
        wrapper = PlaywrightLocator(mock_locator)

        await wrapper.wait_for(state="visible", timeout=5000)

        mock_locator.wait_for.assert_called_once_with(state="visible", timeout=5000)

    @pytest.mark.asyncio
    async def test_click(self) -> None:
        """Test click delegates to Playwright locator."""
        mock_locator = AsyncMock()
        wrapper = PlaywrightLocator(mock_locator)

        await wrapper.click()

        mock_locator.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_fill(self) -> None:
        """Test fill delegates to Playwright locator."""
        mock_locator = AsyncMock()
        wrapper = PlaywrightLocator(mock_locator)

        await wrapper.fill("test value")

        mock_locator.fill.assert_called_once_with("test value")

    @pytest.mark.asyncio
    async def test_text_content(self) -> None:
        """Test text_content delegates to Playwright locator."""
        mock_locator = AsyncMock()
        mock_locator.text_content.return_value = "Hello World"
        wrapper = PlaywrightLocator(mock_locator)

        result = await wrapper.text_content(timeout=3000)

        assert result == "Hello World"
        mock_locator.text_content.assert_called_once_with(timeout=3000)

    @pytest.mark.asyncio
    async def test_text_content_returns_none(self) -> None:
        """Test text_content can return None."""
        mock_locator = AsyncMock()
        mock_locator.text_content.return_value = None
        wrapper = PlaywrightLocator(mock_locator)

        result = await wrapper.text_content()

        assert result is None

    def test_locator(self) -> None:
        """Test locator returns wrapped child locator."""
        mock_child = MagicMock()
        mock_locator = MagicMock()
        mock_locator.locator.return_value = mock_child
        wrapper = PlaywrightLocator(mock_locator)

        result = wrapper.locator("div.container")

        assert isinstance(result, PlaywrightLocator)
        mock_locator.locator.assert_called_once_with("div.container")

    def test_get_by_role(self) -> None:
        """Test get_by_role returns wrapped child locator."""
        mock_child = MagicMock()
        mock_locator = MagicMock()
        mock_locator.get_by_role.return_value = mock_child
        wrapper = PlaywrightLocator(mock_locator)

        result = wrapper.get_by_role("button", name="Submit", exact=True, level=None)

        assert isinstance(result, PlaywrightLocator)
        mock_locator.get_by_role.assert_called_once_with(
            "button", name="Submit", exact=True, level=None
        )

    def test_get_by_role_with_pattern(self) -> None:
        """Test get_by_role with regex pattern."""
        mock_child = MagicMock()
        mock_locator = MagicMock()
        mock_locator.get_by_role.return_value = mock_child
        wrapper = PlaywrightLocator(mock_locator)

        pattern = re.compile(r"Submit.*")
        result = wrapper.get_by_role("button", name=pattern)

        assert isinstance(result, PlaywrightLocator)
        mock_locator.get_by_role.assert_called_once_with(
            "button", name=pattern, exact=False, level=None
        )


class TestPlaywrightKeyboard:
    """Test PlaywrightKeyboard wrapper."""

    @pytest.mark.asyncio
    async def test_press(self) -> None:
        """Test press delegates to Playwright keyboard."""
        mock_page = AsyncMock()
        wrapper = PlaywrightKeyboard(mock_page)

        await wrapper.press("Enter")

        mock_page.keyboard.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_press_combination(self) -> None:
        """Test pressing key combinations."""
        mock_page = AsyncMock()
        wrapper = PlaywrightKeyboard(mock_page)

        await wrapper.press("Control+a")

        mock_page.keyboard.press.assert_called_once_with("Control+a")

    @pytest.mark.asyncio
    async def test_type(self) -> None:
        """Test type delegates to Playwright keyboard."""
        mock_page = AsyncMock()
        wrapper = PlaywrightKeyboard(mock_page)

        await wrapper.type("Hello World")

        mock_page.keyboard.type.assert_called_once_with("Hello World")


class TestPlaywrightResponse:
    """Test PlaywrightResponse wrapper."""

    def test_url_property(self) -> None:
        """Test url property returns response URL."""
        mock_response = Mock()
        mock_response.url = "https://example.com/api/data"
        wrapper = PlaywrightResponse(mock_response)

        assert wrapper.url == "https://example.com/api/data"

    def test_status_property(self) -> None:
        """Test status property returns HTTP status."""
        mock_response = Mock()
        mock_response.status = 200
        wrapper = PlaywrightResponse(mock_response)

        assert wrapper.status == 200

    def test_headers_property(self) -> None:
        """Test headers property returns response headers."""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        wrapper = PlaywrightResponse(mock_response)

        assert wrapper.headers == {"content-type": "application/json"}

    @pytest.mark.asyncio
    async def test_json(self) -> None:
        """Test json method returns parsed JSON."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {"result": "success"}
        wrapper = PlaywrightResponse(mock_response)

        result = await wrapper.json()

        assert result == {"result": "success"}
        mock_response.json.assert_called_once()


class TestPlaywrightDriver:
    """Test PlaywrightDriver wrapper."""

    def test_keyboard_property(self) -> None:
        """Test keyboard property returns KeyboardProtocol."""
        mock_page = MagicMock()
        driver = PlaywrightDriver(mock_page)

        keyboard = driver.keyboard

        assert isinstance(keyboard, PlaywrightKeyboard)

    def test_get_by_role(self) -> None:
        """Test get_by_role returns wrapped locator."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_page.get_by_role.return_value = mock_locator
        driver = PlaywrightDriver(mock_page)

        result = driver.get_by_role("button", name="Click me")

        assert isinstance(result, PlaywrightLocator)
        mock_page.get_by_role.assert_called_once_with(
            "button", name="Click me", exact=False, level=None
        )

    def test_get_by_role_with_level(self) -> None:
        """Test get_by_role with heading level."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_page.get_by_role.return_value = mock_locator
        driver = PlaywrightDriver(mock_page)

        result = driver.get_by_role("heading", name="Title", level=2)

        assert isinstance(result, PlaywrightLocator)
        mock_page.get_by_role.assert_called_once_with(
            "heading", name="Title", exact=False, level=2
        )

    def test_locator(self) -> None:
        """Test locator returns wrapped locator."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_page.locator.return_value = mock_locator
        driver = PlaywrightDriver(mock_page)

        result = driver.locator("div.container")

        assert isinstance(result, PlaywrightLocator)
        mock_page.locator.assert_called_once_with("div.container")

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self) -> None:
        """Test wait_for_timeout delegates to page."""
        mock_page = AsyncMock()
        driver = PlaywrightDriver(mock_page)

        await driver.wait_for_timeout(1000)

        mock_page.wait_for_timeout.assert_called_once_with(1000)

    @pytest.mark.asyncio
    async def test_wait_for_load_state(self) -> None:
        """Test wait_for_load_state delegates to page."""
        mock_page = AsyncMock()
        driver = PlaywrightDriver(mock_page)

        await driver.wait_for_load_state("networkidle")

        mock_page.wait_for_load_state.assert_called_once_with("networkidle")

    @pytest.mark.asyncio
    async def test_wait_for_load_state_default(self) -> None:
        """Test wait_for_load_state with default state."""
        mock_page = AsyncMock()
        driver = PlaywrightDriver(mock_page)

        await driver.wait_for_load_state()

        mock_page.wait_for_load_state.assert_called_once_with("domcontentloaded")

    @pytest.mark.asyncio
    async def test_evaluate(self) -> None:
        """Test evaluate delegates to page."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = 42
        driver = PlaywrightDriver(mock_page)

        result = await driver.evaluate("() => 40 + 2")

        assert result == 42
        mock_page.evaluate.assert_called_once_with("() => 40 + 2")

    @pytest.mark.asyncio
    async def test_on_response_handler(self) -> None:
        """Test on() wraps response handler."""
        mock_page = MagicMock()
        driver = PlaywrightDriver(mock_page)

        async def handler(response) -> None:
            pass

        driver.on("response", handler)

        # Verify handler was registered (wrapped)
        mock_page.on.assert_called_once()
        call_args = mock_page.on.call_args
        assert call_args[0][0] == "response"
        assert callable(call_args[0][1])

    @pytest.mark.asyncio
    async def test_on_wraps_response_objects(self) -> None:
        """Test that on() wraps Playwright Response objects."""
        mock_page = MagicMock()
        driver = PlaywrightDriver(mock_page)

        received_response = None

        async def handler(response) -> None:
            nonlocal received_response
            received_response = response

        driver.on("response", handler)

        # Get the wrapped handler that was registered
        wrapped_handler = mock_page.on.call_args[0][1]

        # Create a mock Playwright response
        mock_pw_response = Mock()
        mock_pw_response.url = "https://example.com"
        mock_pw_response.status = 200

        # Call the wrapped handler
        await wrapped_handler(mock_pw_response)

        # Verify the handler received a wrapped response
        assert received_response is not None
        assert isinstance(received_response, PlaywrightResponse)
        assert received_response.url == "https://example.com"

    def test_remove_listener(self) -> None:
        """Test remove_listener removes the wrapped handler."""
        mock_page = MagicMock()
        driver = PlaywrightDriver(mock_page)

        async def handler(response) -> None:
            pass

        # Register handler
        driver.on("response", handler)

        # Remove handler
        driver.remove_listener("response", handler)

        # Verify wrapped handler was removed
        mock_page.remove_listener.assert_called_once()
        call_args = mock_page.remove_listener.call_args
        assert call_args[0][0] == "response"

    def test_remove_listener_unknown_handler(self) -> None:
        """Test remove_listener with unregistered handler does nothing."""
        mock_page = MagicMock()
        driver = PlaywrightDriver(mock_page)

        async def handler(response) -> None:
            pass

        # Try to remove handler that was never registered
        driver.remove_listener("response", handler)

        # Should not call page.remove_listener
        mock_page.remove_listener.assert_not_called()
