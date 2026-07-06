"""Tests for serial_receiver.py"""

import ssb_backend.serial_receiver as sr
from ssb_backend.serial_receiver import(
    CONFIRM_BYTE,
    REQUEST_BYTE,
    _HEADER_LINE,
    _looks_like_ssb,
    _process_connection,
    accumulate_stream,
    save_csv
)

_HEADER = "timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw"
_ROW = "0,33.12,41.55,29.80,2100"
_ROW2 = "1000,33.20,41.60,29.90,2095"
_SHORT_ROW = "2000,33.30,41.70" # truncated final row


# helpers ---------------------------------------------------------------------
def _build_lines(rows, *, header=True, end=True, error=None):
    """Assemble ordered list of text lines"""
    lines = []
    if error is not None:
        return [error]
    if header:
        lines.append(_HEADER)
    lines.extend(rows)
    if end:
        lines.append("END")
    return lines


class FakeSerial:
    """
    Minimal stand in for a pyserial connection.

    Records every write() so tests can assert byte ordering.
    Scripts readline() to pop pre seeded byte lines.
    """

    def __init__(self, lines):
        self.reads = [f"{ln}\n".encode("utf-8") for ln in lines]
        self.writes = []


    def reset_input_buffer(self):
        pass


    def write(self, data):
        self.writes.append(data)

    
    def flush(self):
        pass


    def readline(self):
        return self.reads.pop(0) if self.reads else b""
    



# accumulate_stream ------------------------------------------------------------
def test_accumulate_wellformed_complete():
    result = accumulate_stream(_build_lines([_ROW, _ROW2]))

    assert result.complete is True
    assert result.device_reported_error is False
    assert result.csv_text == f"{_HEADER}\n{_ROW}\n{_ROW2}\n"


def test_accumulate_no_end_is_incomplete():
    result = accumulate_stream(_build_lines([_ROW, _ROW2], end=False))

    assert result.complete is False
    assert result.device_reported_error is False


def test_accumulate_device_error():
    result = accumulate_stream(["ERROR: no session"])

    assert result.device_reported_error is True
    assert result.complete is False
    assert result.csv_text == ""


def test_accumulate_strips_crlf():
    crlf_lines = [f"{_HEADER}\r\n", f"{_ROW}\r\n", "END\r\n"]
    result = accumulate_stream(crlf_lines)

    assert result.complete is True
    assert result.csv_text == f"{_HEADER}\n{_ROW}\n"




# looks_like_ssb ----------------------------------------------------------------
def test_looks_like_ssb_true():
    assert _looks_like_ssb(_HEADER)
    assert _looks_like_ssb("#gsr_baseline=2048")
    assert _looks_like_ssb(_ROW) 


def test_looks_like_ssb_false():
    assert not _looks_like_ssb("hello world")
    assert not _looks_like_ssb("1,2,3")




# save csv ----------------------------------------------------------------
def test_save_csv_default_timestamp_roundtrip(tmp_path):
    text = f"{_HEADER}\n{_ROW}\n"
    path = save_csv(text, tmp_path)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == text
    assert path.parent == tmp_path
    assert path.name.startswith("session_") and path.name.endswith(".csv")




# process connection ----------------------------------------------------------------
def test_complete_saves_before_confirm(tmp_path, monkeypatch):
    ser = FakeSerial(_build_lines([_ROW, _ROW2]))
    snapshot = {}

    def spy_save(csv_text, *args, **kwargs):
        snapshot["writes_at_save"] = list(ser.writes)  # capture state at save time
        return tmp_path / "session_fake.csv"

    monkeypatch.setattr(sr, "save_csv", spy_save)

    outcome = _process_connection(ser)

    assert outcome.confirmed is True
    assert outcome.saved_path == tmp_path / "session_fake.csv"
    # save ran, and 'C' had NOT been written yet at that moment:
    assert REQUEST_BYTE in snapshot["writes_at_save"]
    assert CONFIRM_BYTE not in snapshot["writes_at_save"]
    # ...and 'C' was written afterward.
    assert CONFIRM_BYTE in ser.writes


def test_no_end_never_confirms():
    ser = FakeSerial(_build_lines([_ROW, _ROW2], end=False))

    outcome = _process_connection(ser)

    assert outcome.confirmed is False
    assert outcome.saved_path is None
    assert CONFIRM_BYTE not in ser.writes


def test_truncated_final_row_still_confirms(tmp_path, monkeypatch):
    ser = FakeSerial(_build_lines([_ROW, _SHORT_ROW]))  # short row, then proper END
    monkeypatch.setattr(sr, "save_csv", lambda *a, **k: tmp_path / "session_fake.csv")

    outcome = _process_connection(ser)

    assert outcome.confirmed is True # truncation does NOT block 'C'
    assert CONFIRM_BYTE in ser.writes
    assert outcome.parse_result.truncated_final_row is True
    assert outcome.parse_result.malformed_row_count == 0


def test_device_error_no_save_no_confirm():
    ser = FakeSerial(["ERROR: no session"])

    outcome = _process_connection(ser)

    assert outcome.detected is True
    assert outcome.saved_path is None
    assert outcome.confirmed is False
    assert CONFIRM_BYTE not in ser.writes


def test_looks_like_ssb_gsr_baseline_with_space():
    assert _looks_like_ssb("# gsr_baseline=2454") is True


def test_looks_like_ssb_gsr_baseline_no_space():
    assert _looks_like_ssb("#gsr_baseline=2454") is True