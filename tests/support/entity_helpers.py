"""Shared test helpers for constructing mock config entries and light entities."""

from unittest.mock import AsyncMock, MagicMock


BASE_CONFIG_DATA = {
    "type": "light",
    "name": "Test Light",
    "entity_id": "light.test_real_light",
    "color_picker": [255, 249, 216],
    "priority": 1000,
    "delay": True,
    "delay_time": {"seconds": 5},
    "peek_time": {"seconds": 5},
}


def make_config_entry(*, data_overrides: dict | None = None, options: dict | None = None):
    entry = MagicMock()
    entry.data = {**BASE_CONFIG_DATA, **(data_overrides or {})}
    entry.options = options if options is not None else {}
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
    return entity
