"""Tests for ColorInfo dataclass."""

from copy import copy
from dataclasses import replace

import pytest

from custom_components.color_notify.utils.light_sequence import ColorInfo, _interpolate
from custom_components.color_notify.const import OFF_RGB, WARM_WHITE_RGB


class TestColorInfoDefaults:
    """Test ColorInfo default construction."""

    def test_default_rgb(self):
        c = ColorInfo()
        assert c.rgb == WARM_WHITE_RGB

    def test_default_brightness(self):
        assert ColorInfo().brightness == 100.0

    def test_default_kelvin_is_none(self):
        assert ColorInfo().kelvin is None

    def test_default_transition_is_none(self):
        assert ColorInfo().transition is None

    def test_default_explicit_brightness_is_none(self):
        assert ColorInfo().explicit_brightness is None

    def test_off_rgb_color(self):
        c = ColorInfo(rgb=OFF_RGB, brightness=0)
        assert c.rgb == (0, 0, 0)
        assert c.brightness == 0

    def test_equality(self):
        a = ColorInfo(rgb=(255, 0, 0), kelvin=2700, transition=0.5, explicit_brightness=128)
        b = ColorInfo(rgb=(255, 0, 0), kelvin=2700, transition=0.5, explicit_brightness=128)
        assert a == b

    def test_inequality(self):
        a = ColorInfo(rgb=(255, 0, 0))
        b = ColorInfo(rgb=(0, 255, 0))
        assert a != b

    def test_copy(self):
        original = ColorInfo(rgb=(100, 200, 50), kelvin=3000, transition=1.0, explicit_brightness=200)
        copied = copy(original)
        assert copied == original
        assert copied is not original

    def test_dataclass_replace(self):
        original = ColorInfo(rgb=(255, 0, 0), kelvin=2700)
        replaced = replace(original, kelvin=3200)
        assert replaced.kelvin == 3200
        assert replaced.rgb == (255, 0, 0)
        assert original.kelvin == 2700  # original unchanged


class TestLightParams:
    """Test ColorInfo.light_params property."""

    def test_rgb_default(self):
        c = ColorInfo(rgb=(255, 0, 0))
        params = c.light_params
        assert params == {"rgb_color": (255, 0, 0)}

    def test_kelvin_only(self):
        c = ColorInfo(kelvin=2700)
        params = c.light_params
        assert params == {"color_temp_kelvin": 2700}
        assert "rgb_color" not in params

    def test_rgb_used_when_no_kelvin(self):
        c = ColorInfo(rgb=(255, 0, 0))
        params = c.light_params
        assert params == {"rgb_color": (255, 0, 0)}
        assert "color_temp_kelvin" not in params

    def test_transition_with_rgb(self):
        c = ColorInfo(rgb=(0, 255, 0), transition=0.5)
        params = c.light_params
        assert params["transition"] == 0.5
        assert params["rgb_color"] == (0, 255, 0)

    def test_transition_with_kelvin(self):
        c = ColorInfo(kelvin=2200, transition=2.0)
        params = c.light_params
        assert params == {"color_temp_kelvin": 2200, "transition": 2.0}

    def test_no_transition_by_default(self):
        c = ColorInfo(rgb=(0, 255, 0))
        assert "transition" not in c.light_params

    def test_explicit_brightness(self):
        c = ColorInfo(rgb=(255, 0, 0), explicit_brightness=128)
        params = c.light_params
        assert params["brightness"] == 128

    def test_explicit_brightness_zero(self):
        c = ColorInfo(rgb=(255, 0, 0), explicit_brightness=0)
        params = c.light_params
        assert params["brightness"] == 0

    def test_no_brightness_by_default(self):
        c = ColorInfo(rgb=(255, 0, 0))
        assert "brightness" not in c.light_params

    def test_all_fields_kelvin_mode(self):
        c = ColorInfo(kelvin=2200, transition=1.0, explicit_brightness=200)
        params = c.light_params
        assert params == {
            "color_temp_kelvin": 2200,
            "transition": 1.0,
            "brightness": 200,
        }
        assert "rgb_color" not in params

    def test_all_fields_rgb_mode(self):
        c = ColorInfo(rgb=(0, 0, 255), transition=1.0, explicit_brightness=200)
        params = c.light_params
        assert params["rgb_color"] == (0, 0, 255)
        assert params["transition"] == 1.0
        assert params["brightness"] == 200
        assert "color_temp_kelvin" not in params

    def test_off_rgb_params(self):
        c = ColorInfo(rgb=OFF_RGB)
        assert c.light_params == {"rgb_color": (0, 0, 0)}

    def test_transition_zero(self):
        c = ColorInfo(rgb=(255, 0, 0), transition=0)
        # transition=0 is falsy but not None, should still be included
        assert c.light_params["transition"] == 0

    def test_brightness_with_kelvin(self):
        c = ColorInfo(kelvin=2700, explicit_brightness=64)
        params = c.light_params
        assert params == {"color_temp_kelvin": 2700, "brightness": 64}
        assert "rgb_color" not in params


class TestInterpolation:
    """Test ColorInfo.interpolated_to method."""

    def test_rgb_interpolation_midpoint(self):
        a = ColorInfo(rgb=(0, 0, 0), brightness=0)
        b = ColorInfo(rgb=(100, 200, 100), brightness=100)
        mid = a.interpolated_to(b, 0.5)
        assert mid.rgb == (50, 100, 50)
        assert mid.brightness == 50

    def test_rgb_interpolation_quarter(self):
        a = ColorInfo(rgb=(0, 0, 0), brightness=0)
        b = ColorInfo(rgb=(100, 200, 100), brightness=100)
        q = a.interpolated_to(b, 0.25)
        assert q.rgb == (25, 50, 25)
        assert q.brightness == 25

    def test_kelvin_interpolation(self):
        a = ColorInfo(kelvin=2200, brightness=50)
        b = ColorInfo(kelvin=3200, brightness=100)
        mid = a.interpolated_to(b, 0.5)
        assert mid.kelvin == 2700
        assert mid.brightness == 75.0

    def test_kelvin_interpolation_preserves_explicit_brightness(self):
        a = ColorInfo(kelvin=2200, explicit_brightness=128)
        b = ColorInfo(kelvin=3200)
        mid = a.interpolated_to(b, 0.5)
        assert mid.explicit_brightness == 128

    def test_rgb_interpolation_preserves_explicit_brightness(self):
        a = ColorInfo(rgb=(0, 0, 0), explicit_brightness=200)
        b = ColorInfo(rgb=(255, 255, 255))
        mid = a.interpolated_to(b, 0.5)
        assert mid.explicit_brightness == 200

    def test_mixed_kelvin_rgb_falls_back_to_rgb(self):
        a = ColorInfo(rgb=(255, 0, 0), brightness=100)
        b = ColorInfo(kelvin=3200, brightness=100)
        mid = a.interpolated_to(b, 0.5)
        assert mid.kelvin is None

    def test_mixed_rgb_kelvin_other_direction(self):
        a = ColorInfo(kelvin=2200, brightness=100)
        b = ColorInfo(rgb=(255, 0, 0), brightness=100)
        mid = a.interpolated_to(b, 0.5)
        # a has kelvin, b doesn't -- falls back to RGB
        assert mid.kelvin is None

    def test_interpolation_at_zero(self):
        a = ColorInfo(rgb=(0, 0, 0), brightness=0)
        b = ColorInfo(rgb=(200, 200, 200), brightness=200)
        start = a.interpolated_to(b, 0.0)
        assert start.rgb == (0, 0, 0)
        assert start.brightness == 0

    def test_interpolation_at_one(self):
        a = ColorInfo(rgb=(0, 0, 0), brightness=0)
        b = ColorInfo(rgb=(200, 200, 200), brightness=200)
        end = a.interpolated_to(b, 1.0)
        assert end.rgb == (200, 200, 200)
        assert end.brightness == 200

    def test_kelvin_interpolation_at_endpoints(self):
        a = ColorInfo(kelvin=2200)
        b = ColorInfo(kelvin=4000)
        assert a.interpolated_to(b, 0.0).kelvin == 2200
        assert a.interpolated_to(b, 1.0).kelvin == 4000

    def test_interpolation_does_not_carry_transition(self):
        a = ColorInfo(rgb=(0, 0, 0), transition=0.5)
        b = ColorInfo(rgb=(255, 255, 255), transition=2.0)
        mid = a.interpolated_to(b, 0.5)
        # transition is a per-step property, not interpolated
        assert mid.transition is None


class TestInterpolateHelper:
    """Test the _interpolate utility function."""

    def test_basic(self):
        assert _interpolate((0, 0), (100, 200), 0.5) == (50, 100)

    def test_at_zero(self):
        assert _interpolate((10, 20), (100, 200), 0.0) == (10, 20)

    def test_at_one(self):
        assert _interpolate((10, 20), (100, 200), 1.0) == (100, 200)

    def test_single_element(self):
        assert _interpolate((0,), (100,), 0.75) == (75,)

    def test_truncates_to_int(self):
        result = _interpolate((0,), (3,), 0.5)
        assert result == (1,)  # int(1.5) = 1
