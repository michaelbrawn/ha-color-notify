"""Tests for WrappedLightState — tracks real light state for notification restore.

WrappedLightState solves the post-notification restore problem:
- Before: notifications clear → worker sends WARM_WHITE_RGB at brightness 255
- After: notifications clear → worker sends the actual pre-notification light state

It also eliminates _startup_quiet by decoupling state tracking from commands:
- On startup, WrappedLightState reads the current state without sending commands
- The "restore" concept only applies after a notification has played
"""

import pytest

from custom_components.color_notify.utils.wrapped_light_state import WrappedLightState


class FakeAttributes(dict):
    """Dict subclass that also supports .get() like HA state attributes."""
    pass


class FakeState:
    """Minimal HA state object for testing."""

    def __init__(self, state: str, attributes: dict | None = None):
        self.state = state
        self.attributes = FakeAttributes(attributes or {})


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestInit:

    def test_starts_empty(self):
        ws = WrappedLightState()
        assert ws.is_on is False
        assert ws.has_state is False
        assert ws.restore_params == {}

    def test_not_frozen_initially(self):
        ws = WrappedLightState()
        assert ws.is_frozen is False


# ---------------------------------------------------------------------------
# State Updates
# ---------------------------------------------------------------------------

class TestUpdate:

    def test_update_from_on_state(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        assert ws.is_on is True
        assert ws.has_state is True

    def test_update_from_off_state(self):
        ws = WrappedLightState()
        ws.update(FakeState("off"))
        assert ws.is_on is False
        assert ws.has_state is True

    def test_update_replaces_previous(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 100}))
        ws.update(FakeState("on", {"brightness": 200}))
        assert ws.restore_params["brightness"] == 200

    def test_update_ignored_when_frozen(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 150}))
        ws.freeze()
        ws.update(FakeState("on", {"brightness": 255}))
        assert ws.restore_params["brightness"] == 150

    def test_update_resumes_after_unfreeze(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 150}))
        ws.freeze()
        ws.update(FakeState("on", {"brightness": 255}))
        ws.unfreeze()
        ws.update(FakeState("on", {"brightness": 80}))
        assert ws.restore_params["brightness"] == 80


# ---------------------------------------------------------------------------
# Freeze / Unfreeze
# ---------------------------------------------------------------------------

class TestFreeze:

    def test_freeze_captures_state(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        ws.freeze()
        assert ws.is_frozen is True
        params = ws.restore_params
        assert params["brightness"] == 150
        assert params["color_temp"] == 370

    def test_unfreeze_clears_frozen(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 150}))
        ws.freeze()
        ws.unfreeze()
        assert ws.is_frozen is False

    def test_freeze_without_state_is_safe(self):
        ws = WrappedLightState()
        ws.freeze()
        assert ws.is_frozen is True
        assert ws.restore_params == {}

    def test_double_freeze_is_idempotent(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 150}))
        ws.freeze()
        ws.freeze()  # Should not reset the captured state
        assert ws.restore_params["brightness"] == 150


# ---------------------------------------------------------------------------
# Restore Params — color_temp mode
# ---------------------------------------------------------------------------

class TestRestoreColorTemp:

    def test_color_temp_mode(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        params = ws.restore_params
        assert params == {"brightness": 150, "color_temp": 370}
        assert "rgb_color" not in params
        assert "hs_color" not in params

    def test_color_temp_no_brightness(self):
        """Light that only reports color_temp (e.g. brightness not in attributes)."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        params = ws.restore_params
        assert params == {"color_temp": 370}


# ---------------------------------------------------------------------------
# Restore Params — xy mode (Hue lights)
# ---------------------------------------------------------------------------

class TestRestoreXY:

    def test_xy_mode(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 200,
            "xy_color": [0.4573, 0.41],
            "color_mode": "xy",
        }))
        params = ws.restore_params
        assert params == {"brightness": 200, "xy_color": [0.4573, 0.41]}

    def test_xy_mode_with_hs_fallback(self):
        """If xy_color missing but hs_color present, use hs."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 200,
            "hs_color": [50.769, 15.294],
            "color_mode": "xy",
        }))
        params = ws.restore_params
        assert params == {"brightness": 200, "hs_color": [50.769, 15.294]}


# ---------------------------------------------------------------------------
# Restore Params — hs mode
# ---------------------------------------------------------------------------

class TestRestoreHS:

    def test_hs_mode(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 180,
            "hs_color": [270, 100],
            "color_mode": "hs",
        }))
        params = ws.restore_params
        assert params == {"brightness": 180, "hs_color": [270, 100]}


# ---------------------------------------------------------------------------
# Restore Params — rgb mode
# ---------------------------------------------------------------------------

class TestRestoreRGB:

    def test_rgb_mode(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 128,
            "rgb_color": [255, 0, 128],
            "color_mode": "rgb",
        }))
        params = ws.restore_params
        assert params == {"brightness": 128, "rgb_color": [255, 0, 128]}


# ---------------------------------------------------------------------------
# Restore Params — brightness-only mode
# ---------------------------------------------------------------------------

class TestRestoreBrightness:

    def test_brightness_only(self):
        """Caseta dimmers: brightness only, no color."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 64,
            "color_mode": "brightness",
        }))
        params = ws.restore_params
        assert params == {"brightness": 64}


# ---------------------------------------------------------------------------
# Restore Params — off state
# ---------------------------------------------------------------------------

class TestRestoreOff:

    def test_off_state_returns_empty(self):
        """Off lights don't need restore params — just turn_off."""
        ws = WrappedLightState()
        ws.update(FakeState("off"))
        assert ws.restore_params == {}

    def test_off_after_on_returns_empty(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {"brightness": 150}))
        ws.update(FakeState("off"))
        assert ws.restore_params == {}


# ---------------------------------------------------------------------------
# Restore Params — edge cases
# ---------------------------------------------------------------------------

class TestRestoreEdgeCases:

    def test_unknown_color_mode_falls_back_to_available_attrs(self):
        """If color_mode is something we don't handle, include what we can."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 100,
            "color_mode": "rgbww",
            "rgb_color": [255, 200, 150],
        }))
        params = ws.restore_params
        assert params["brightness"] == 100
        assert params["rgb_color"] == [255, 200, 150]

    def test_no_color_attributes_returns_brightness_only(self):
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 200,
        }))
        params = ws.restore_params
        assert params == {"brightness": 200}

    def test_none_values_excluded(self):
        """Attributes present but None should not appear in restore_params."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": None,
            "color_mode": "color_temp",
        }))
        params = ws.restore_params
        assert "color_temp" not in params
        assert params == {"brightness": 150}


# ---------------------------------------------------------------------------
# Startup scenario (decoupled from commands)
# ---------------------------------------------------------------------------

class TestStartupDecoupling:

    def test_initial_state_read_no_freeze(self):
        """On startup, read state but don't freeze — no notification active."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        assert ws.has_state is True
        assert ws.is_frozen is False
        assert ws.restore_params == {"brightness": 150, "color_temp": 370}

    def test_startup_off_then_notification(self):
        """Light was off at startup, notification plays, restores to off."""
        ws = WrappedLightState()
        ws.update(FakeState("off"))
        ws.freeze()  # Notification starts
        assert ws.is_on is False
        # After notification: caller checks is_on to decide turn_off vs turn_on

    def test_startup_on_then_notification_then_restore(self):
        """Light on at startup, notification plays, restore to original."""
        ws = WrappedLightState()
        ws.update(FakeState("on", {
            "brightness": 150,
            "color_temp": 370,
            "color_mode": "color_temp",
        }))
        ws.freeze()
        # Notification changes light — these updates are ignored
        ws.update(FakeState("on", {
            "brightness": 255,
            "rgb_color": [128, 0, 255],
            "color_mode": "rgb",
        }))
        # Restore should return original state, not notification state
        params = ws.restore_params
        assert params == {"brightness": 150, "color_temp": 370}
        assert ws.is_on is True
