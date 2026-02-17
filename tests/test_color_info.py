"""Tests for ColorInfo dataclass."""

from copy import copy
from dataclasses import replace

import pytest

from custom_components.color_notify.utils.light_sequence import ColorInfo, _interpolate
from custom_components.color_notify.const import OFF_RGB, WARM_WHITE_RGB


class TestColorInfoDefaults:

    def test_default_rgb(self):
        assert ColorInfo().rgb == WARM_WHITE_RGB

    def test_default_brightness(self):
        assert ColorInfo().brightness == 100.0

    @pytest.mark.parametrize("field", ["kelvin", "transition", "explicit_brightness"])
    def test_optional_fields_default_to_none(self, field):
        assert getattr(ColorInfo(), field) is None

    def test_off_rgb_color(self):
        c = ColorInfo(rgb=OFF_RGB, brightness=0)
        assert c.rgb == (0, 0, 0)
        assert c.brightness == 0

    def test_equality(self):
        kwargs = dict(rgb=(255, 0, 0), kelvin=2700, transition=0.5, explicit_brightness=128)
        assert ColorInfo(**kwargs) == ColorInfo(**kwargs)

    def test_inequality(self):
        assert ColorInfo(rgb=(255, 0, 0)) != ColorInfo(rgb=(0, 255, 0))

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
        assert original.kelvin == 2700


class TestLightParams:

    def test_rgb_only(self):
        assert ColorInfo(rgb=(255, 0, 0)).light_params == {"rgb_color": (255, 0, 0)}

    def test_kelvin_only(self):
        params = ColorInfo(kelvin=2700).light_params
        assert params == {"color_temp_kelvin": 2700}
        assert "rgb_color" not in params

    @pytest.mark.parametrize("color_kwargs,expected_params", [
        (dict(rgb=(0, 255, 0), transition=0.5), {"rgb_color": (0, 255, 0), "transition": 0.5}),
        (dict(kelvin=2200, transition=2.0), {"color_temp_kelvin": 2200, "transition": 2.0}),
        (dict(rgb=(255, 0, 0), explicit_brightness=128), {"rgb_color": (255, 0, 0), "brightness": 128}),
        (dict(kelvin=2700, explicit_brightness=64), {"color_temp_kelvin": 2700, "brightness": 64}),
    ], ids=["transition_rgb", "transition_kelvin", "brightness_rgb", "brightness_kelvin"])
    def test_optional_params(self, color_kwargs, expected_params):
        assert ColorInfo(**color_kwargs).light_params == expected_params

    @pytest.mark.parametrize("field", ["transition", "brightness"])
    def test_not_included_by_default(self, field):
        assert field not in ColorInfo(rgb=(255, 0, 0)).light_params

    def test_explicit_brightness_zero(self):
        assert ColorInfo(rgb=(255, 0, 0), explicit_brightness=0).light_params["brightness"] == 0

    def test_transition_zero(self):
        assert ColorInfo(rgb=(255, 0, 0), transition=0).light_params["transition"] == 0

    def test_all_fields_kelvin_mode(self):
        params = ColorInfo(kelvin=2200, transition=1.0, explicit_brightness=200).light_params
        assert params == {"color_temp_kelvin": 2200, "transition": 1.0, "brightness": 200}
        assert "rgb_color" not in params

    def test_all_fields_rgb_mode(self):
        params = ColorInfo(rgb=(0, 0, 255), transition=1.0, explicit_brightness=200).light_params
        assert params == {"rgb_color": (0, 0, 255), "transition": 1.0, "brightness": 200}
        assert "color_temp_kelvin" not in params


class TestInterpolation:

    @pytest.mark.parametrize("amount,expected_rgb,expected_brightness", [
        (0.0, (0, 0, 0), 0),
        (0.25, (25, 50, 25), 25),
        (0.5, (50, 100, 50), 50),
        (1.0, (100, 200, 100), 100),
    ], ids=["start", "quarter", "midpoint", "end"])
    def test_rgb_interpolation(self, amount, expected_rgb, expected_brightness):
        a = ColorInfo(rgb=(0, 0, 0), brightness=0)
        b = ColorInfo(rgb=(100, 200, 100), brightness=100)
        mid = a.interpolated_to(b, amount)
        assert mid.rgb == expected_rgb
        assert mid.brightness == expected_brightness

    def test_kelvin_interpolation(self):
        a = ColorInfo(kelvin=2200, brightness=50)
        b = ColorInfo(kelvin=3200, brightness=100)
        mid = a.interpolated_to(b, 0.5)
        assert mid.kelvin == 2700
        assert mid.brightness == 75.0

    @pytest.mark.parametrize("amount,expected", [(0.0, 2200), (1.0, 4000)])
    def test_kelvin_interpolation_at_endpoints(self, amount, expected):
        a = ColorInfo(kelvin=2200)
        b = ColorInfo(kelvin=4000)
        assert a.interpolated_to(b, amount).kelvin == expected

    @pytest.mark.parametrize("use_kelvin", [True, False], ids=["kelvin", "rgb"])
    def test_interpolation_preserves_explicit_brightness(self, use_kelvin):
        kwargs = dict(kelvin=2200) if use_kelvin else dict(rgb=(0, 0, 0))
        end_kwargs = dict(kelvin=3200) if use_kelvin else dict(rgb=(255, 255, 255))
        a = ColorInfo(**kwargs, explicit_brightness=128)
        b = ColorInfo(**end_kwargs)
        assert a.interpolated_to(b, 0.5).explicit_brightness == 128

    def test_mixed_kelvin_rgb_falls_back_to_rgb(self):
        a = ColorInfo(rgb=(255, 0, 0), brightness=100)
        b = ColorInfo(kelvin=3200, brightness=100)
        assert a.interpolated_to(b, 0.5).kelvin is None

    def test_mixed_rgb_kelvin_other_direction(self):
        a = ColorInfo(kelvin=2200, brightness=100)
        b = ColorInfo(rgb=(255, 0, 0), brightness=100)
        assert a.interpolated_to(b, 0.5).kelvin is None

    def test_interpolation_does_not_carry_transition(self):
        a = ColorInfo(rgb=(0, 0, 0), transition=0.5)
        b = ColorInfo(rgb=(255, 255, 255), transition=2.0)
        assert a.interpolated_to(b, 0.5).transition is None


class TestInterpolateHelper:

    @pytest.mark.parametrize("start,end,amount,expected", [
        ((0, 0), (100, 200), 0.5, (50, 100)),
        ((10, 20), (100, 200), 0.0, (10, 20)),
        ((10, 20), (100, 200), 1.0, (100, 200)),
        ((0,), (100,), 0.75, (75,)),
        ((0,), (3,), 0.5, (1,)),
    ], ids=["midpoint", "at_zero", "at_one", "single_element", "truncates_to_int"])
    def test_interpolate(self, start, end, amount, expected):
        assert _interpolate(start, end, amount) == expected
