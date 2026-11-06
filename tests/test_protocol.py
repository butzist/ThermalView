import numpy as np

from thermalview.frame import encode_payload
from thermalview.protocol import (
    FRAME_MAGIC,
    PAYLOAD_SIZE,
    CMD_SET_EMISSIVITY,
    CMD_START,
    CMD_STOP,
    FrameParser,
    FramePayload,
    StatusEvent,
    command,
    emissivity_command,
    iter_payloads,
    start_command,
    stop_command,
)

HEADER = FRAME_MAGIC + b"\xaa\xbb"


def make_payload(offset: int = 0) -> bytes:
    raw = (np.arange(1024, dtype=np.uint16) + offset).reshape(32, 32)
    return encode_payload(raw)


def test_command_bytes_match_android_app():
    assert start_command() == bytes.fromhex("008004000000")
    assert stop_command() == bytes.fromhex("008005000000")
    assert emissivity_command(0.98) == bytes.fromhex("00800300010062")
    assert command(CMD_START) == bytes.fromhex("008004000000")
    assert command(CMD_SET_EMISSIVITY, b"\x5a").hex() == "0080030001005a"


def test_command_rejects_invalid_values():
    for value in (-0.01, 1.01, 2):
        try:
            emissivity_command(value)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"{value} should be rejected")


def test_parser_handles_byte_at_a_time_chunks():
    payload = make_payload()
    parser = FrameParser()
    events = []
    for byte in HEADER + payload:
        events.extend(parser.feed(bytes([byte])))

    assert len(events) == 1
    assert isinstance(events[0], FramePayload)
    assert events[0].data == payload


def test_parser_handles_multiple_frames_in_one_chunk():
    first = make_payload(0)
    second = make_payload(500)
    events = FrameParser().feed(HEADER + first + HEADER + second)

    assert [event.data for event in events] == [first, second]


def test_parser_reports_status_before_frame():
    payload = make_payload()
    stream = b"\x00\x90\x04\x00\x00\x00" + HEADER + payload
    events = FrameParser().feed(stream)

    assert isinstance(events[0], StatusEvent)
    assert events[0].subtype == 4
    assert isinstance(events[1], FramePayload)
    assert events[1].data == payload


def test_parser_resynchronises_after_truncated_frame():
    good = make_payload()
    truncated = make_payload(900)[:1000]
    events = FrameParser().feed(HEADER + truncated + HEADER + good)

    assert len(events) == 1
    assert events[0].data == good


def test_parser_drops_leading_garbage():
    payload = make_payload()
    events = FrameParser().feed(b"\x01\x02\x03garbage" + HEADER + payload)

    assert len(events) == 1
    assert events[0].data == payload


def test_iter_payloads_reads_recorded_stream():
    first = make_payload(0)
    second = make_payload(7)
    assert iter_payloads(HEADER + first + HEADER + second) == [first, second]


def test_payload_size_is_32x32_uint16():
    assert PAYLOAD_SIZE == 2048
    assert len(make_payload()) == PAYLOAD_SIZE
