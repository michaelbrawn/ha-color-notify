"""Tests for notification restore — the post-notification state problem.

Problem: After a notification clears, Color Notify restores the wrapped light
to WARM_WHITE_RGB at brightness 255 instead of the actual pre-notification state.

Solution: WrappedLightState tracks the real light state and provides correct
restore_params. The entity uses these instead of the hardcoded LIGHT_ON_SEQUENCE.

These tests validate the integration between WrappedLightState and the entity's
restore logic without running the full worker loop.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.color_notify.const import (
    CONF_RESTORE_POWER,
    WARM_WHITE_RGB,
)
from custom_components.color_notify.utils.wrapped_light_state import WrappedLightState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeState:
    """Minimal HA state object."""

    def __init__(self, state: str, attributes: dict | None = None):
        self.state = state
        self.attributes = attributes or {}


def make_config_entry(restore_power: bool = False):
    entry = MagicMock()
    entry.data = {
        "type": "light",
        "name": "Test Light",
        "entity_id": "light.test_real_light",
        "color_picker": list(WARM_WHITE_RGB),
        "dynamic_priority": True,
        "priority": 1000,
        "delay": True,
        "delay_time": {"seconds": 5},
        "peek_time": {"seconds": 5},
        CONF_RESTORE_POWER: restore_power,
    }
    entry.options = {}
    entry.title = "[Light] Test Light"
    entry.async_create_background_task = MagicMock()
    entry.async_on_unload = MagicMock()
    return entry


def make_light_entity(config_entry):
    from custom_components.color_notify.light import NotificationLightEntity

    entity = NotificationLightEntity(
        unique_id="test_unique_id",
        wrapped_entity_id="light.test_real_light",
        config_entry=config_entry,
    )
    entity.hass = MagicMock()
    entity.hass.states.get.return_value = None
    entity.hass.bus.async_fire = MagicMock()
    entity.hass.async_create_task = MagicMock()
    entity.hass.services.async_call = AsyncMock()
    entity.async_write_ha_state = MagicMock()
    entity.async_schedule_update_ha_state = MagicMock()
    entity._wrapped_init_done = True
    return entity


async def simulate_restore(entity, wrapped_state: WrappedLightState):
    """Simulate what happens when notifications clear and base state restores.

    This mirrors _process_sequence_list behavior when top sequence is base state.
    Instead of sending LIGHT_ON_SEQUENCE.color (WARM_WHITE_RGB), uses tracked state.
    """
    if wrapped_state.is_on:
        params = wrapped_state.restore_params
        if params:
            await entity._wrapped_light_turn_on(**params)
        else:
            # ON but no params — just turn on with no args
            await entity._wrapped_light_turn_on()
    else:
        await entity._wrapped_light_turn_off()
    wrapped_state.unfreeze()


# ---------------------------------------------------------------------------
# Restore to color_temp (most common Hue scenario)
# ---------------------------------------------------------------------------

class TestRestoreColorTemp:

    @pytest.mark.asyncio
    async def test_restore_to_warm_white_2700k(self):
        """Hue light at 2700K / brightness 150 → notification → restore."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()
        tracker.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,  # mireds for ~2700K
            "color_mode": "color_temp",
        }))
        tracker.freeze()

        await simulate_restore(entity, tracker)

        entity.hass.services.async_call.assert_called_once()
        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 150
        assert service_data["color_temp"] == 370
        assert "rgb_color" not in service_data

    @pytest.mark.asyncio
    async def test_restore_to_cool_white_3200k(self):
        """Hue light at 3200K / brightness 255 → notification → restore."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()
        tracker.update(FakeState("on", {
            "brightness": 255,
            "color_temp": 312,  # mireds for ~3200K
            "color_mode": "color_temp",
        }))
        tracker.freeze()

        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 255
        assert service_data["color_temp"] == 312


# ---------------------------------------------------------------------------
# Restore to xy mode (Hue default)
# ---------------------------------------------------------------------------

class TestRestoreXY:

    @pytest.mark.asyncio
    async def test_restore_xy_warm_white(self):
        """Hue light in xy mode (warm white) → notification → restore."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()
        tracker.update(FakeState("on", {
            "brightness": 254,
            "xy_color": [0.4573, 0.41],
            "hs_color": [50.769, 15.294],
            "color_mode": "xy",
        }))
        tracker.freeze()

        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 254
        assert service_data["xy_color"] == [0.4573, 0.41]
        assert "rgb_color" not in service_data


# ---------------------------------------------------------------------------
# Restore OFF light
# ---------------------------------------------------------------------------

class TestRestoreOff:

    @pytest.mark.asyncio
    async def test_restore_off_sends_turn_off(self):
        """Light was off before notification → restore turns it off."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()
        tracker.update(FakeState("off"))
        tracker.freeze()

        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        # Should be a turn_off call
        assert entity.hass.services.async_call.call_count == 1
        call_args = entity.hass.services.async_call.call_args[0]
        assert call_args[1] == "turn_off"


# ---------------------------------------------------------------------------
# Restore brightness-only (Caseta dimmers)
# ---------------------------------------------------------------------------

class TestRestoreBrightnessOnly:

    @pytest.mark.asyncio
    async def test_restore_caseta_dimmer(self):
        """Caseta dimmer: brightness only, no color mode."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()
        tracker.update(FakeState("on", {
            "brightness": 64,
            "color_mode": "brightness",
        }))
        tracker.freeze()

        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 64
        assert "color_temp" not in service_data
        assert "rgb_color" not in service_data


# ---------------------------------------------------------------------------
# Startup: no commands sent
# ---------------------------------------------------------------------------

class TestStartupNoCommands:

    @pytest.mark.asyncio
    async def test_startup_reads_state_only(self):
        """On startup, tracker reads state but entity sends no commands."""
        config_entry = make_config_entry(restore_power=False)
        entity = make_light_entity(config_entry)

        tracker = WrappedLightState()

        # Simulate startup: wrapped light is on with known state
        tracker.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))

        # No freeze, no restore — just tracking
        assert tracker.has_state is True
        assert tracker.is_on is True
        # Entity should NOT have sent any commands
        entity.hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_startup_off_no_commands(self):
        """Light was off at startup — no commands sent."""
        config_entry = make_config_entry(restore_power=False)
        entity = make_light_entity(config_entry)

        tracker = WrappedLightState()
        tracker.update(FakeState("off"))

        assert tracker.has_state is True
        assert tracker.is_on is False
        entity.hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# Freeze during notification prevents state tracking
# ---------------------------------------------------------------------------

class TestFreezeBlocksTracking:

    @pytest.mark.asyncio
    async def test_notification_changes_ignored_during_freeze(self):
        """State changes during notification don't corrupt restore state."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()

        # Pre-notification: warm white
        tracker.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        tracker.freeze()

        # Notification sends purple to the light — state changes arrive
        tracker.update(FakeState("on", {
            "brightness": 255,
            "rgb_color": [128, 0, 255],
            "hs_color": [270, 100],
            "color_mode": "hs",
        }))

        # Restore should use pre-notification state, not purple
        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 150
        assert service_data["color_temp"] == 370
        assert "rgb_color" not in service_data

    @pytest.mark.asyncio
    async def test_multiple_notifications_preserve_original_state(self):
        """Multiple notifications in sequence: always restore to original."""
        config_entry = make_config_entry()
        entity = make_light_entity(config_entry)
        entity._startup_quiet = False

        tracker = WrappedLightState()

        # Original state
        tracker.update(FakeState("on", {
            "brightness": 100,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        tracker.freeze()

        # First notification plays purple
        tracker.update(FakeState("on", {
            "brightness": 200,
            "rgb_color": [128, 0, 255],
            "color_mode": "rgb",
        }))
        # Second notification plays green (higher priority)
        tracker.update(FakeState("on", {
            "brightness": 255,
            "rgb_color": [0, 255, 0],
            "color_mode": "rgb",
        }))

        # All notifications clear — restore to ORIGINAL state
        await simulate_restore(entity, tracker)

        call_kwargs = entity.hass.services.async_call.call_args
        service_data = call_kwargs[1].get("service_data") or call_kwargs[0][2]
        assert service_data["brightness"] == 100
        assert service_data["color_temp"] == 370


# ---------------------------------------------------------------------------
# Contrast with old behavior (WARM_WHITE_RGB)
# ---------------------------------------------------------------------------

class TestContrastOldBehavior:

    def test_old_behavior_always_warm_white(self):
        """Document: old code always restores to WARM_WHITE_RGB regardless."""
        from custom_components.color_notify.utils.light_sequence import ColorInfo

        # This is what LIGHT_ON_SEQUENCE.color.light_params returns
        old_restore = ColorInfo(WARM_WHITE_RGB, 255).light_params
        assert old_restore == {"rgb_color": WARM_WHITE_RGB}
        # Note: brightness 255 hardcoded, no color_temp, no original state

    @pytest.mark.asyncio
    async def test_new_behavior_restores_actual_state(self):
        """New code restores the actual pre-notification state."""
        tracker = WrappedLightState()
        tracker.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        tracker.freeze()

        new_restore = tracker.restore_params
        assert new_restore == {"brightness": 150, "color_temp": 370}
        # No WARM_WHITE_RGB, no brightness 255 — actual state preserved
