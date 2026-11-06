import numpy as np

from thermalview.palette import (
    apply_palette,
    blue_orange,
    blue_yellow,
    iron_red,
    palette_names,
    rainbow,
    resolve_palette,
    white_hot,
)


def rgb(function, value):
    return tuple(int(channel) for channel in function(np.array([value]))[0])


def test_palette_order_matches_app_color_type():
    assert palette_names() == (
        "iron_red",
        "rainbow",
        "white_hot",
        "blue_orange",
        "blue_yellow",
    )
    assert resolve_palette(0) is iron_red
    assert resolve_palette("iron") is iron_red
    assert resolve_palette("white") is white_hot


def test_iron_red_piecewise_values():
    assert rgb(iron_red, 0.0) == (0, 0, 0)
    assert rgb(iron_red, 0.25) == (45, 0, 30)
    assert rgb(iron_red, 0.5) == (90, 0, 60)
    assert rgb(iron_red, 0.6) == (255, 153, 0)
    assert rgb(iron_red, 0.9) == (255, 253, 238)


def test_white_hot_truncates_like_the_native_cast():
    assert rgb(white_hot, 0.5) == (127, 127, 127)
    assert rgb(white_hot, 1.0) == (255, 255, 255)


def test_blue_orange_values():
    assert rgb(blue_orange, 0.25) == (63, 0, 191)
    assert rgb(blue_orange, 0.75) == (191, 90, 63)


def test_blue_yellow_values():
    assert rgb(blue_yellow, 0.25) == (17, 17, 50)
    assert rgb(blue_yellow, 0.6) == (255, 255, 0)
    assert rgb(blue_yellow, 0.9) == (255, 253, 238)


def test_rainbow_is_stepped():
    assert rgb(rainbow, 0.1) == (0, 0, 0)
    assert rgb(rainbow, 0.3) == (26, 35, 126)
    assert rgb(rainbow, 0.45) == (63, 81, 181)
    assert rgb(rainbow, 0.55) == (76, 175, 80)
    assert rgb(rainbow, 0.7) == (118, 255, 3)
    assert rgb(rainbow, 0.78) == (255, 235, 59)
    assert rgb(rainbow, 0.9) == (244, 67, 54)


def test_apply_palette_shape_dtype_and_clamping():
    temperatures = np.array([[0.0, 5.0], [10.0, 15.0]])
    rgb_array = apply_palette(temperatures, 5.0, 10.0, "iron_red")

    assert rgb_array.shape == (2, 2, 3)
    assert rgb_array.dtype == np.uint8
    # 5 C maps to t=0, 10 C to t=1, out-of-range values clamp.
    assert tuple(rgb_array[0, 0]) == (0, 0, 0)
    assert tuple(rgb_array[1, 1]) == (255, 253, 238)
    assert tuple(rgb_array[0, 1]) == (0, 0, 0)
    assert tuple(rgb_array[1, 0]) == (255, 253, 238)


def test_flat_frame_does_not_divide_by_zero():
    flat = np.full((4, 4), 21.0)
    rgb_array = apply_palette(flat, 21.0, 21.0, "iron_red")
    assert np.all(rgb_array == 0)
