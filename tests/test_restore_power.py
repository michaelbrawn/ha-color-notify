"""Tests for restore_power config option (startup white blast fix)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.color_notify.const import CONF_RESTORE_POWER


class FakeState:
    def __init__(self, state: str):
        self.state = state


def make_config_entry(restore_power: bool | None = None):
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
    entity.async_write_ha_state = MagicMock()
    entity.async_schedule_update_ha_state = MagicMock()
    entity.async_turn_on = AsyncMock()
    entity.async_turn_off = AsyncMock()
    return entity


async def simulate_restore(entity, last_state: str | None):
    """Mirrors the restore logic in async_added_to_hass."""
    entity.async_get_last_state = AsyncMock(
        return_value=FakeState(last_state) if last_state else None,
    )
    restored_state = await entity.async_get_last_state()
    if restored_state:
        entity._attr_is_on = restored_state.state == "on"
        entity.async_schedule_update_ha_state(True)
        if entity._restore_power:
            if entity.is_on:
                entity.hass.async_create_task(entity.async_turn_on())
            else:
                entity.hass.async_create_task(entity.async_turn_off())


class TestRestorePowerConfig:

    @pytest.mark.parametrize("restore_power,expected", [
        (None, False),
        (False, False),
        (True, True),
    ], ids=["default_missing", "explicit_false", "explicit_true"])
    def test_restore_power_value(self, restore_power, expected):
        entry = make_config_entry(restore_power=restore_power)
        entity = make_light_entity(entry)
        assert entity._restore_power is expected


class TestRestorePowerDisabled:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("last_state", ["on", "off"])
    async def test_no_commands_sent(self, last_state):
        entity = make_light_entity(make_config_entry(restore_power=False))
        await simulate_restore(entity, last_state)

        assert entity._attr_is_on == (last_state == "on")
        entity.hass.async_create_task.assert_not_called()


class TestRestorePowerEnabled:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("last_state", ["on", "off"])
    async def test_command_sent(self, last_state):
        entity = make_light_entity(make_config_entry(restore_power=True))
        await simulate_restore(entity, last_state)

        assert entity._attr_is_on == (last_state == "on")
        entity.hass.async_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_previous_state_does_nothing(self):
        entity = make_light_entity(make_config_entry(restore_power=True))
        await simulate_restore(entity, None)

        entity.hass.async_create_task.assert_not_called()
        entity.async_schedule_update_ha_state.assert_not_called()
