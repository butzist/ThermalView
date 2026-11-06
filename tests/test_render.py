import numpy as np
from PIL import Image

from thermalview.frame import decode_payload, encode_payload
from thermalview.render import (
    frame_to_image,
    frame_to_rgb,
    save_frame,
    save_npy,
    temperature_csv,
)


def make_frame(temp: float = 25.0):
    raw = np.full((32, 32), int(temp * 10), dtype=np.uint16)
    return decode_payload(encode_payload(raw))


def test_frame_to_rgb_shape_and_dtype():
    rgb = frame_to_rgb(make_frame())
    assert rgb.shape == (32, 32, 3)
    assert rgb.dtype == np.uint8


def test_frame_to_image_scales_to_requested_size():
    image = frame_to_image(make_frame(), size=160)
    assert isinstance(image, Image.Image)
    assert image.size == (160, 160)
    assert image.mode == "RGB"


def test_app_auto_range_changes_mapping():
    raw = np.zeros((32, 32), dtype=np.uint16)
    raw[0, 0] = 50  # 5 C, range 0..5 < 6 C -> app uses max 7.5 C
    frame = decode_payload(encode_payload(raw))

    honest = frame_to_rgb(frame, palette="white_hot")
    app_like = frame_to_rgb(frame, palette="white_hot", app_auto_range=True)

    assert tuple(honest[0, 0]) == (255, 255, 255)
    assert tuple(app_like[0, 0]) == (170, 170, 170)


def test_save_frame_and_npy(tmp_path):
    frame = make_frame()
    png = save_frame(frame, tmp_path / "nested" / "frame.png", size=64)
    npy = save_npy(frame, tmp_path / "frame.npy")

    assert png.exists() and png.stat().st_size > 0
    assert npy.exists()
    assert np.load(npy).shape == (32, 32)


def test_temperature_csv_has_one_row_per_pixel_row():
    text = temperature_csv(make_frame(21.5))
    rows = text.strip().splitlines()
    assert len(rows) == 32
    assert len(rows[0].split(",")) == 32
    assert rows[0].split(",")[0] == "21.5"
