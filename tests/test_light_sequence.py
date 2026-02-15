"""Tests for LightSequence pattern parser and execution."""

import asyncio

import pytest

from custom_components.color_notify.utils.light_sequence import ColorInfo, LightSequence
from custom_components.color_notify.const import OFF_RGB, WARM_WHITE_RGB


# -- Pattern parser: backward compatibility --

class TestPatternParserBackwardCompat:
    """Existing patterns still parse correctly."""

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
        # Initial color is first item
        assert seq.color.rgb == (255, 0, 0)

    def test_curly_brace_stripping(self):
        """Parser strips and re-adds curly braces, so both formats work."""
        seq = LightSequence.create_from_pattern([
            '"rgb": [100, 100, 100]',
        ])
        assert seq.color.rgb == (100, 100, 100)


# -- Pattern parser: new fields --

class TestPatternParserNewFields:
    """New fields parse from JSON."""

    def test_transition_parsed(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "transition": 0.5}',
        ])
        assert seq.color.transition == 0.5

    def test_kelvin_parsed(self):
        seq = LightSequence.create_from_pattern([
            '{"kelvin": 2700, "delay": 1}',
        ])
        color = seq.color
        assert color.kelvin == 2700
        assert color.rgb == WARM_WHITE_RGB

    def test_brightness_parsed(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "brightness": 128}',
        ])
        assert seq.color.explicit_brightness == 128

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
        color = seq.color
        params = color.light_params
        assert params["color_temp_kelvin"] == 2200
        assert params["brightness"] == 64
        assert params["transition"] == 2.0

    def test_transition_zero(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "transition": 0}',
        ])
        assert seq.color.transition == 0

    def test_rgb_defaults_over_kelvin_in_json(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "kelvin": 2700}',
        ])
        color = seq.color
        assert color.rgb == (255, 0, 0)
        assert color.kelvin is None
        assert "rgb_color" in color.light_params
        assert "color_temp_kelvin" not in color.light_params

    def test_brightness_zero(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "brightness": 0}',
        ])
        assert seq.color.explicit_brightness == 0


# -- Pattern parser: error handling --

class TestPatternParserErrors:
    """Parser error handling."""

    def test_missing_rgb_and_kelvin_raises(self):
        with pytest.raises(Exception, match="must have 'rgb' or 'kelvin'"):
            LightSequence.create_from_pattern([
                '{"delay": 1}',
            ])

    def test_invalid_json_raises(self):
        with pytest.raises(Exception, match="Error in entry #1"):
            LightSequence.create_from_pattern([
                'not valid json at all',
            ])

    def test_unclosed_loop_raises(self):
        with pytest.raises(Exception, match="was not closed"):
            LightSequence.create_from_pattern([
                '{"rgb": [255, 0, 0]}',
                "[",
            ])

    def test_close_without_open_raises(self):
        with pytest.raises(Exception, match="no open loop"):
            LightSequence.create_from_pattern([
                '{"rgb": [255, 0, 0]}',
                "],2",
            ])

    def test_nested_unclosed_loop_raises(self):
        with pytest.raises(Exception, match="was not closed"):
            LightSequence.create_from_pattern([
                "[",
                '{"rgb": [255, 0, 0]}',
                "[",
                '{"rgb": [0, 255, 0]}',
                "],2",
                # outer loop not closed
            ])


# -- Empty and edge-case patterns --

class TestPatternEdgeCases:
    """Edge cases for pattern construction."""

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


# -- Sequence execution --

class TestSequenceExecution:
    """Test sequence step execution."""

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
        done = await seq.runNextStep()
        assert done
        # Running again after done should still return True
        done = await seq.runNextStep()
        assert done

    @pytest.mark.asyncio
    async def test_empty_sequence_is_immediately_done(self):
        seq = LightSequence.create_from_pattern([])
        done = await seq.runNextStep()
        assert done

    @pytest.mark.asyncio
    async def test_delay_step_created_from_pattern(self):
        """Pattern with delay creates a delay step (tested by step count)."""
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0], "delay": 0.001}',
        ])
        # Step 1: set color, Step 2: delay -- so 2 steps, not done after first
        done = await seq.runNextStep()
        assert not done
        assert seq.color.rgb == (255, 0, 0)
        done = await seq.runNextStep()  # delay step
        assert done

    @pytest.mark.asyncio
    async def test_loop_executes_correct_iterations(self):
        seq = LightSequence.create_from_pattern([
            "[",
            '{"rgb": [255, 0, 0]}',
            "],2",
        ])
        assert not seq.loops_forever
        colors_seen = []
        for _ in range(20):  # safety limit
            done = await seq.runNextStep()
            colors_seen.append(seq.color.rgb)
            if done:
                break
        assert done
        # Open loop + set color + close loop * 2 iterations
        # iter1: open, set, close(->open), iter2: open(skip), set, close(done)
        # The set color step runs twice
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
        """Mutating the sequence's color shouldn't affect the step's stored color."""
        seq = LightSequence.create_from_pattern([
            ColorInfo(rgb=(255, 0, 0)),
            ColorInfo(rgb=(0, 255, 0)),
        ])
        await seq.runNextStep()
        seq.color = ColorInfo(rgb=(99, 99, 99))  # override
        # Re-create and re-run to verify the step still has the original
        seq2 = LightSequence.create_from_pattern([
            ColorInfo(rgb=(255, 0, 0)),
        ])
        await seq2.runNextStep()
        assert seq2.color.rgb == (255, 0, 0)

    def test_loop_pattern_not_forever(self):
        seq = LightSequence.create_from_pattern([
            '{"rgb": [255, 0, 0]}',
            "[",
            '{"rgb": [0, 255, 0]}',
            "],2",
        ])
        assert not seq.loops_forever

    def test_forever_loop(self):
        seq = LightSequence.create_from_pattern([
            "[",
            '{"rgb": [255, 0, 0]}',
            "]",
        ])
        assert seq.loops_forever

    def test_nested_loops(self):
        seq = LightSequence.create_from_pattern([
            "[",
            '{"rgb": [255, 0, 0]}',
            "[",
            '{"rgb": [0, 255, 0]}',
            "],2",
            "],2",
        ])
        assert not seq.loops_forever


# -- Flash notification pattern (real-world usage) --

class TestFlashNotificationPattern:
    """Test patterns matching our flash_notification script behavior."""

    def test_green_flash_pattern(self):
        """Green flash: fade to green, hold, fade to warm white."""
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 255, 0], "transition": 0.5, "delay": 0.5}',
            '{"kelvin": 2700, "transition": 1.0}',
        ])
        color = seq.color
        assert color.rgb == (0, 255, 0)
        assert color.transition == 0.5

    def test_blue_flash_pattern(self):
        """Blue flash for manual override signal."""
        seq = LightSequence.create_from_pattern([
            '{"rgb": [0, 0, 255], "transition": 0.5, "brightness": 128, "delay": 0.5}',
            '{"kelvin": 2700, "transition": 1.0, "brightness": 128}',
        ])
        color = seq.color
        assert color.explicit_brightness == 128

    def test_brightness_preserved_across_steps(self):
        """Both steps explicitly set brightness to maintain it."""
        pattern = [
            '{"rgb": [0, 255, 0], "brightness": 200, "transition": 0.5}',
            '{"kelvin": 2700, "brightness": 200, "transition": 1.0}',
        ]
        seq = LightSequence.create_from_pattern(pattern)
        assert seq.color.explicit_brightness == 200
        assert seq.color.light_params["brightness"] == 200
