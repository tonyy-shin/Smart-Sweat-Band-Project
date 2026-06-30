"""Tests for parser.py"""

import pytest

from ssb_backend.parser import parse_session_csv, ParseResult

_HEADER = "timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw"

# csv ------------------------------------------------------------------------
wellformed_csv = ["0,33.12,41.55,29.80,2100", "1000,33.20,41.60,29.90,2095"]
baseline = 2048

truncated_csv = ["0,33.12,41.55,29.80,2100", "1000,33.20,41.60"]

malformed_csv = [
            "0,33.12,41.55,29.80,2100",
            "1,2,3,4", # middle row: 4 fields, not last
            "2000,33.30,41.70,29.95,2080",
        ]

# ----------------------------------------------------------------------------

def _build_csv(data_rows, *, baseline=None, header=True):
    """Assemble a CSV body"""
    lines = []
    if baseline is not None:
        lines.append(f"# gsr_baseline={baseline}")
    if header:
        lines.append(_HEADER)
    lines.extend(data_rows)
    return "\n".join(lines) + "\n"


# tests -----------------------------------------------------------------------
def test_wellformed_csv():
    csv = _build_csv(wellformed_csv, baseline=baseline)
    result = parse_session_csv(csv)

    assert len(result.samples) == 2
    assert result.samples[0] == {
        "timestamp_ms": 0,
        "skin_temp_c": 33.12,
        "humidity_pct": 41.55,
        "chamber_temp_c": 29.80,
        "gsr_raw": 2100,
    }
    assert result.gsr_baseline == 2048
    assert result.truncated_final_row is False
    assert result.malformed_row_count == 0


def test_truncated_final_row():
    csv = _build_csv(truncated_csv, baseline=baseline)
    result = parse_session_csv(csv)

    assert len(result.samples) == 1
    assert result.truncated_final_row is True
    assert result.malformed_row_count == 0


def test_malformed_middle_row():
    csv = _build_csv(malformed_csv, baseline=baseline)
    result = parse_session_csv(csv)

    assert len(result.samples) == 2
    assert result.malformed_row_count == 1
    assert result.truncated_final_row is False


def test_baseline_override():
    csv = _build_csv(["0,33.12,41.55,29.80,2100"], baseline=baseline)
    result = parse_session_csv(csv, gsr_baseline=999)

    assert result.gsr_baseline == 999


def test_empty_string():
    assert parse_session_csv("") == ParseResult([], None, False, 0)


def test_bytes_input():
    text = _build_csv(["0,33.12,41.55,29.80,2100"], baseline=baseline)

    assert parse_session_csv(text.encode("utf-8")) == parse_session_csv(text)


def test_crlf_line_endings():
    text_lf = _build_csv(
        ["0,33.12,41.55,29.80,2100", "1000,33.20,41.60,29.90,2095"],
        baseline=baseline,
    )
    text_crlf = text_lf.replace("\n", "\r\n")
    
    assert parse_session_csv(text_crlf) == parse_session_csv(text_lf)


def test_stray_end_sentinel():
    csv = _build_csv(
        ["0,33.12,41.55,29.80,2100", "1000,33.20,41.60,29.90,2095", "END"],
        baseline=baseline,
    )
    result = parse_session_csv(csv)

    assert len(result.samples) == 2
    assert result.malformed_row_count == 0
    assert result.truncated_final_row is False


def test_no_baseline_no_override():
    csv = _build_csv(["0,33.12,41.55,29.80,2100"])  # no comment line, no param
    result = parse_session_csv(csv)

    assert result.gsr_baseline is None