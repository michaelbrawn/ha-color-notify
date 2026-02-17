"""Tests for kelvin support in async_turn_on and state_attributes."""

from unittest.mock import AsyncMock

import pytest

from custom_components.color_notify.const import WARM_WHITE_RGB
from tests.support.entity_helpers import make_config_entry, make_light_entity


def _make_kelvin_entity():
    entry = make_config_entry(options={"dynamic_priority": False})
    entity = make_light_entity(entry)
    # Kelvin tests inspect the sequence built by the real async_turn_on
    entity._add_sequence = AsyncMock()
    return entity


class TestAsyncTurnOnKelvin:

    @pytest.mark.asyncio
    async def test_kelvin_stores_kelvin_value(self):
        entity = _make_kelvin_entity()
        await entity.async_turn_on(color_temp_kelvin=2700)

        assert entity._last_on_kelvin == 2700

    @pytest.mark.asyncio
    async def test_kelvin_resets_rgb_to_warm_white(self):
        entity = _make_kelvin_entity()
        entity._last_on_rgb = (255, 0, 0)
        await entity.async_turn_on(color_temp_kelvin=4000)

        assert entity._last_on_rgb == WARM_WHITE_RGB

    @pytest.mark.asyncio
    async def test_kelvin_builds_kelvin_color_info(self):
        entity = _make_kelvin_entity()
        await entity.async_turn_on(color_temp_kelvin=3500)

        entity._add_sequence.assert_called_once()
        _, sequence = entity._add_sequence.call_args.args
        color = sequence._pattern[0]
        assert color.kelvin == 3500
        assert color.rgb == WARM_WHITE_RGB  # default, not used

    @pytest.mark.asyncio
    async def test_rgb_clears_kelvin(self):
        entity = _make_kelvin_entity()
        entity._last_on_kelvin = 2700
        await entity.async_turn_on(rgb_color=(255, 0, 0))

        assert entity._last_on_kelvin is None

    @pytest.mark.asyncio
    async def test_hs_clears_kelvin(self):
        entity = _make_kelvin_entity()
        entity._last_on_kelvin = 2700
        await entity.async_turn_on(hs_color=(120, 100))

        assert entity._last_on_kelvin is None

    @pytest.mark.asyncio
    async def test_no_args_preserves_kelvin_mode(self):
        entity = _make_kelvin_entity()
        entity._last_on_kelvin = 2700
        await entity.async_turn_on()

        entity._add_sequence.assert_called_once()
        _, sequence = entity._add_sequence.call_args.args
        color = sequence._pattern[0]
        assert color.kelvin == 2700

    @pytest.mark.asyncio
    async def test_no_args_preserves_rgb_mode(self):
        entity = _make_kelvin_entity()
        entity._last_on_rgb = (100, 50, 25)
        entity._last_on_kelvin = None
        await entity.async_turn_on()

        entity._add_sequence.assert_called_once()
        _, sequence = entity._add_sequence.call_args.args
        color = sequence._pattern[0]
        assert color.kelvin is None
        assert color.rgb == (100, 50, 25)


class TestStateAttributesKelvin:

    def test_kelvin_mode_reports_color_temp(self):
        entity = _make_kelvin_entity()
        entity._attr_is_on = True
        entity._last_on_kelvin = 2700

        attrs = entity.state_attributes
        assert attrs["color_mode"] == "color_temp"
        assert attrs["color_temp_kelvin"] == 2700

    def test_rgb_mode_reports_rgb(self):
        entity = _make_kelvin_entity()
        entity._attr_is_on = True
        entity._last_on_kelvin = None
        entity._last_on_rgb = (255, 0, 0)

        attrs = entity.state_attributes
        assert attrs["color_mode"] == "rgb"
        assert attrs["rgb_color"] == (255, 0, 0)

    def test_kelvin_mode_includes_rgb_from_conversion(self):
        entity = _make_kelvin_entity()
        entity._attr_is_on = True
        entity._last_on_kelvin = 2700

        attrs = entity.state_attributes
        assert "rgb_color" in attrs
        r, g, b = attrs["rgb_color"]
        # 2700K is warm — red should be high, blue should be lower
        assert r > 200

    def test_off_returns_empty(self):
        entity = _make_kelvin_entity()
        entity._attr_is_on = False

        attrs = entity.state_attributes
        assert attrs == {}

    def test_no_function_ref_bug(self):
        """Regression: line 848 used to assign function ref instead of value."""
        entity = _make_kelvin_entity()
        entity._attr_is_on = True
        entity._last_on_kelvin = None

        attrs = entity.state_attributes
        for key, val in attrs.items():
            assert not callable(val), f"{key} has callable value: {val}"


class TestSupportedColorModes:

    def test_includes_rgb_and_color_temp(self):
        entity = _make_kelvin_entity()
        modes = entity.supported_color_modes
        assert "rgb" in modes
        assert "color_temp" in modes
