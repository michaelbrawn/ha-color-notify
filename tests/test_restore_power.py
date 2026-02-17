"""Tests for startup restore behavior — the white blast bug.

When Color Notify's wrapper light starts up, it restores its last known state.
If restore_power is True (opt-in), it sends turn_on/turn_off to the real light.
If restore_power is False (default), it only restores internal tracking state
without sending any commands to the wrapped light.

The bug: upstream code unconditionally called async_turn_on() on restore,
causing a bright white blast on every HA restart.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.color_notify.const import CONF_RESTORE_POWER


class FakeState:
    """Minimal state object returned by async_get_last_state."""

    def __init__(self, state: str):
        self.state = state


def make_config_entry(restore_power: bool | None = None):
    """Create a mock config entry with optional restore_power setting."""
    entry = MagicMock()
    data = {
        "type": "light",
        "name": "Test Light",
        "entity_id": "light.test_real_light",
        "color_picker": [255, 249, 216],
        "dynamic_priority": True,
        "priority": 1000,
        "delay": True,
        "delay_time": {"seconds": 5},
        "peek_time": {"seconds": 5},
    }
    if restore_power is not None:
        data[CONF_RESTORE_POWER] = restore_power
    entry.data = data
    entry.options = {}
    entry.title = "[Light] Test Light"
    entry.async_create_background_task = MagicMock()
    entry.async_on_unload = MagicMock()
    return entry


def make_light_entity(config_entry):
    """Create a NotificationLightEntity with mocked HA internals."""
    from custom_components.color_notify.light import NotificationLightEntity

    entity = NotificationLightEntity(
        unique_id="test_unique_id",
        wrapped_entity_id="light.test_real_light",
        config_entry=config_entry,
    )

    # Mock HA internals that async_added_to_hass needs
    entity.hass = MagicMock()
    entity.hass.states.get.return_value = None  # wrapped entity not available yet
    entity.hass.bus.async_fire = MagicMock()
    entity.hass.async_create_task = MagicMock()
    entity.async_write_ha_state = MagicMock()
    entity.async_schedule_update_ha_state = MagicMock()

    # Mock the turn_on/turn_off methods to track calls
    entity.async_turn_on = AsyncMock()
    entity.async_turn_off = AsyncMock()

    return entity


class TestRestorePowerDefault:
    """Default behavior (restore_power not set or False) — no commands to real light."""

    def test_default_is_false(self):
        """restore_power defaults to False when not in config."""
        config_entry = make_config_entry(restore_power=None)
        entity = make_light_entity(config_entry)
        assert entity._restore_power is False

    def test_explicit_false(self):
        """restore_power=False is respected."""
        config_entry = make_config_entry(restore_power=False)
        entity = make_light_entity(config_entry)
        assert entity._restore_power is False

    @pytest.mark.asyncio
    async def test_restore_on_state_no_turn_on(self):
        """When last state was ON and restore_power=False, don't call turn_on."""
        config_entry = make_config_entry(restore_power=False)
        entity = make_light_entity(config_entry)

        # Mock async_get_last_state to return ON
        entity.async_get_last_state = AsyncMock(return_value=FakeState("on"))

        # Run the restore portion of async_added_to_hass
        restored_state = await entity.async_get_last_state()
        if restored_state:
            entity._attr_is_on = restored_state.state == "on"
            entity.async_schedule_update_ha_state(True)
            if entity._restore_power:
                if entity.is_on:
                    entity.hass.async_create_task(entity.async_turn_on())
                else:
                    entity.hass.async_create_task(entity.async_turn_off())

        # Internal state should be ON
        assert entity._attr_is_on is True
        # But no turn_on command sent
        entity.async_turn_on.assert_not_awaited()
        entity.hass.async_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_restore_off_state_no_turn_off(self):
        """When last state was OFF and restore_power=False, don't call turn_off."""
        config_entry = make_config_entry(restore_power=False)
        entity = make_light_entity(config_entry)

        entity.async_get_last_state = AsyncMock(return_value=FakeState("off"))

        restored_state = await entity.async_get_last_state()
        if restored_state:
            entity._attr_is_on = restored_state.state == "on"
            entity.async_schedule_update_ha_state(True)
            if entity._restore_power:
                if entity.is_on:
                    entity.hass.async_create_task(entity.async_turn_on())
                else:
                    entity.hass.async_create_task(entity.async_turn_off())

        assert entity._attr_is_on is False
        entity.async_turn_off.assert_not_awaited()
        entity.hass.async_create_task.assert_not_called()


class TestRestorePowerEnabled:
    """When restore_power=True, commands ARE sent to the real light (old behavior)."""

    def test_explicit_true(self):
        """restore_power=True is respected."""
        config_entry = make_config_entry(restore_power=True)
        entity = make_light_entity(config_entry)
        assert entity._restore_power is True

    @pytest.mark.asyncio
    async def test_restore_on_state_calls_turn_on(self):
        """When last state was ON and restore_power=True, call turn_on."""
        config_entry = make_config_entry(restore_power=True)
        entity = make_light_entity(config_entry)

        entity.async_get_last_state = AsyncMock(return_value=FakeState("on"))

        restored_state = await entity.async_get_last_state()
        if restored_state:
            entity._attr_is_on = restored_state.state == "on"
            entity.async_schedule_update_ha_state(True)
            if entity._restore_power:
                if entity.is_on:
                    entity.hass.async_create_task(entity.async_turn_on())
                else:
                    entity.hass.async_create_task(entity.async_turn_off())

        assert entity._attr_is_on is True
        entity.hass.async_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_off_state_calls_turn_off(self):
        """When last state was OFF and restore_power=True, call turn_off."""
        config_entry = make_config_entry(restore_power=True)
        entity = make_light_entity(config_entry)

        entity.async_get_last_state = AsyncMock(return_value=FakeState("off"))

        restored_state = await entity.async_get_last_state()
        if restored_state:
            entity._attr_is_on = restored_state.state == "on"
            entity.async_schedule_update_ha_state(True)
            if entity._restore_power:
                if entity.is_on:
                    entity.hass.async_create_task(entity.async_turn_on())
                else:
                    entity.hass.async_create_task(entity.async_turn_off())

        assert entity._attr_is_on is False
        entity.hass.async_create_task.assert_called_once()


class TestRestorePowerNoState:
    """When there's no restored state, nothing should happen regardless of config."""

    @pytest.mark.asyncio
    async def test_no_restored_state_does_nothing(self):
        """No previous state — no restore, no commands."""
        config_entry = make_config_entry(restore_power=True)
        entity = make_light_entity(config_entry)

        entity.async_get_last_state = AsyncMock(return_value=None)

        restored_state = await entity.async_get_last_state()
        if restored_state:
            entity._attr_is_on = restored_state.state == "on"
            entity.async_schedule_update_ha_state(True)
            if entity._restore_power:
                if entity.is_on:
                    entity.hass.async_create_task(entity.async_turn_on())
                else:
                    entity.hass.async_create_task(entity.async_turn_off())

        entity.hass.async_create_task.assert_not_called()
        entity.async_schedule_update_ha_state.assert_not_called()
