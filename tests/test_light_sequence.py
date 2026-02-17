"""Tests for LightSequence pattern parser and execution."""

import pytest

from custom_components.color_notify.utils.light_sequence import ColorInfo, LightSequence
from custom_components.color_notify.const import OFF_RGB, WARM_WHITE_RGB


class TestPatternParserBackwardCompat:

    def test_rgb_only_pattern(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "delay": 1}',
        ])
        color = seq.color
        assert color.rgb == (255, 0, 0)
        assert color.kelvin is None
        assert color.transition is None
        assert color.explicit_brightness is None

    def test_color_info_object_pattern(self):
        seq = LightSequence.create_from_pattern([
            ColorInfo(rgb=(0, 255, 0), brightness=100),
        ])
        assert seq.color.rgb == (0, 255, 0)

    def test_rgb_color_attr_key(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb_color": [0, 0, 255]}',
        ])
        assert seq.color.rgb == (0, 0, 255)

    def test_multiple_color_info_objects(self):
        seq = LightSequence.create_from_pattern([
            ColorInfo(rgb=(255, 0, 0)),
            ColorInfo(rgb=(0, 255, 0)),
        ])
        assert seq.color.rgb == (255, 0, 0)

    def test_curly_brace_stripping(self):
        seq = LightSequence.create_from_pattern([
            '"rgb": [100, 100, 100]',
        ])
        assert seq.color.rgb == (100, 100, 100)


class TestPatternParserNewFields:

    @pytest.mark.parametrize("json_str,field,expected", [
        ('{"rgb": [0, 255, 0], "transition": 0.5}', "transition", 0.5),
        ('{"rgb": [255, 0, 0], "brightness": 128}', "explicit_brightness", 128),
        ('{"rgb": [255, 0, 0], "transition": 0}', "transition", 0),
        ('{"rgb": [255, 0, 0], "brightness": 0}', "explicit_brightness", 0),
    ], ids=["transition", "brightness", "transition_zero", "brightness_zero"])
    def test_field_parsed(self, json_str, field, expected):
        seq = LightSequence.create_from_pattern([json_str])
        assert getattr(seq.color, field) == expected

    def test_kelvin_parsed(self):
        seq = LightSequence.create_from_pattern([
            '{"kelvin": 2700, "delay": 1}',
        ])
        assert seq.color.kelvin == 2700
        assert seq.color.rgb == WARM_WHITE_RGB

    def test_all_new_fields(self):
        seq = LightSequence.create_from_pattern([
            '{"kelvin": 3200, "transition": 1.0, "brightness": 200, "delay": 2}',
        ])
        color = seq.color
        assert color.kelvin == 3200
        assert color.transition == 1.0
        assert color.explicit_brightness == 200

    def test_mixed_rgb_and_kelvin_steps(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "transition": 0.5, "delay": 1}',
            '{"kelvin": 2700, "transition": 1}',
        ])
        assert seq.color.rgb == (0, 255, 0)

    def test_kelvin_with_brightness_and_transition(self):
        seq = LightSequence.create_from_pattern([
            '{"kelvin": 2200, "brightness": 64, "transition": 2.0}',
        ])
        params = seq.color.light_params
        assert params == {"color_temp_kelvin": 2200, "brightness": 64, "transition": 2.0}

    def test_rgb_takes_precedence_over_kelvin(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "kelvin": 2700}',
        ])
        color = seq.color
        assert color.rgb == (255, 0, 0)
        assert color.kelvin is None
        assert "rgb_color" in color.light_params
        assert "color_temp_kelvin" not in color.light_params


class TestPatternParserErrors:

    @pytest.mark.parametrize("pattern,match", [
        (['{"delay": 1}'], "must have 'rgb' or 'kelvin'"),
        (["not valid json at all"], "Error in entry #1"),
        (['{"rgb": [255, 0, 0]}', "["], "was not closed"),
        (['{"rgb": [255, 0, 0]}', "],2"], "no open loop"),
    ], ids=["missing_color", "invalid_json", "unclosed_loop", "close_without_open"])
    def test_parse_error(self, pattern, match):
        with pytest.raises(Exception, match=match):
            LightSequence.create_from_pattern(pattern)

    def test_nested_unclosed_loop_raises(self):
        with pytest.raises(Exception, match="was not closed"):
            LightSequence.create_from_pattern([
                "[",
                '{"rgb": [255, 0, 0]}',
                "[",
                '{"rgb": [0, 255, 0]}',
                "],2",
            ])


class TestPatternEdgeCases:

    def test_empty_pattern_gives_off_color(self):
        seq = LightSequence.create_from_pattern([])
        assert seq.color.rgb == OFF_RGB
        assert seq.color.brightness == 0

    def test_single_color_info(self):
        seq = LightSequence.create_from_pattern([
            ColorInfo(rgb=(42, 42, 42)),
        ])
        assert seq.color.rgb == (42, 42, 42)

    def test_whitespace_in_string_items(self):
        seq = LightSequence.create_from_pattern([
            '  {"rgb": [10, 20, 30]}  ',
        ])
        assert seq.color.rgb == (10, 20, 30)

    def test_color_setter(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0]}',
        ])
        seq.color = ColorInfo(rgb=(0, 0, 255))
        assert seq.color.rgb == (0, 0, 255)

    def test_color_getter_returns_copy(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0]}',
        ])
        c1 = seq.color
        c2 = seq.color
        assert c1 == c2
        assert c1 is not c2


class TestSequenceExecution:

    @pytest.mark.asyncio
    async def test_steps_execute_in_order(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0]}',
            '{"kelvin": 2700}',
        ])
        done = await seq.runNextStep()
        assert not done
        assert seq.color.rgb == (255, 0, 0)
        done = await seq.runNextStep()
        assert done
        assert seq.color.kelvin == 2700

    @pytest.mark.asyncio
    async def test_run_past_end_returns_done(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0]}',
        ])
        assert await seq.runNextStep()
        assert await seq.runNextStep()

    @pytest.mark.asyncio
    async def test_empty_sequence_is_immediately_done(self):
        seq = LightSequence.create_from_pattern([])
        assert await seq.runNextStep()

    @pytest.mark.asyncio
    async def test_delay_step_created_from_pattern(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "delay": 0.001}',
        ])
        done = await seq.runNextStep()
        assert not done
        assert seq.color.rgb == (255, 0, 0)
        assert await seq.runNextStep()

    @pytest.mark.asyncio
    async def test_loop_executes_correct_iterations(self):
        seq = LightSequence.create_from_pattern([
            "[",
            '{"rgb": [255, 0, 0]}',
            "],2",
        ])
        assert not seq.loops_forever
        colors_seen = []
        for _ in range(20):
            done = await seq.runNextStep()
            colors_seen.append(seq.color.rgb)
            if done:
                break
        assert done
        assert colors_seen.count((255, 0, 0)) >= 2

    @pytest.mark.asyncio
    async def test_transition_preserved_through_execution(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "transition": 0.5}',
        ])
        await seq.runNextStep()
        assert seq.color.transition == 0.5

    @pytest.mark.asyncio
    async def test_kelvin_step_execution(self):
        seq = LightSequence.create_from_pattern([
            '{"kelvin": 3200, "brightness": 128, "transition": 1.0}',
        ])
        await seq.runNextStep()
        color = seq.color
        assert color.kelvin == 3200
        assert color.explicit_brightness == 128
        assert color.transition == 1.0

    @pytest.mark.asyncio
    async def test_set_color_creates_copy(self):
        seq = LightSequence.create_from_pattern([
            ColorInfo(rgb=(255, 0, 0)),
            ColorInfo(rgb=(0, 255, 0)),
        ])
        await seq.runNextStep()
        seq.color = ColorInfo(rgb=(99, 99, 99))

        seq2 = LightSequence.create_from_pattern([
            ColorInfo(rgb=(255, 0, 0)),
        ])
        await seq2.runNextStep()
        assert seq2.color.rgb == (255, 0, 0)

    @pytest.mark.parametrize("pattern,expected", [
        (['{"rgb": [255, 0, 0]}', "[", '{"rgb": [0, 255, 0]}', "],2"], False),
        (["[", '{"rgb": [255, 0, 0]}', "]"], True),
        (["[", '{"rgb": [255, 0, 0]}', "[", '{"rgb": [0, 255, 0]}', "],2", "],2"], False),
    ], ids=["finite_loop", "infinite_loop", "nested_finite"])
    def test_loops_forever(self, pattern, expected):
        assert LightSequence.create_from_pattern(pattern).loops_forever == expected


class TestFlashNotificationPattern:

    def test_green_flash_pattern(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "transition": 0.5, "delay": 0.5}',
            '{"kelvin": 2700, "transition": 1.0}',
        ])
        assert seq.color.rgb == (0, 255, 0)
        assert seq.color.transition == 0.5

    def test_blue_flash_with_brightness(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 0, 255], "transition": 0.5, "brightness": 128, "delay": 0.5}',
            '{"kelvin": 2700, "transition": 1.0, "brightness": 128}',
        ])
        assert seq.color.explicit_brightness == 128

    def test_brightness_preserved_across_steps(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "brightness": 200, "transition": 0.5}',
            '{"kelvin": 2700, "brightness": 200, "transition": 1.0}',
        ])
        assert seq.color.explicit_brightness == 200
        assert seq.color.light_params["brightness"] == 200
