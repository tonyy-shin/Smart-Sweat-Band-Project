"""
Parser for handling SSB data files

converts the raw session CSV into structured sample dicts

Firmware CSV layout:
    #gsr_baseline=<int>
    timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw
    0,33.12,41.55,29.80,2100
    .
    .
    .
    .
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_COLUMNS = [
    ("timestamp_ms", int),
    ("skin_temp_c", float),
    ("humidity_pct", float),
    ("chamber_temp_c", float),
    ("gsr_raw", int),
]

_EXPECTED_COLS = len(_COLUMNS)

_HEADER_LINE = ",".join(name for name, _ in _COLUMNS)
_BASELINE_RE = re.compile(r"^#\s*gsr_baseline\s*=\s*(\d+)")

@dataclass
class ParseResult:
    samples: list[dict]
    gsr_baseline: int | None
    truncated_final_row: bool
    malformed_row_count: int




def parse_session_csv(
        csv_data: str | bytes, 
        gsr_baseline: int | None = None
    ) -> ParseResult:
    """parse CSV into samples + baseline.

    Args:
        csv_data: CSV body
        gsr_baseline: optional override

    Returns:
        ParseResult with samples, resolved gsr_baseline, and two failure fields       
    """
    if isinstance(csv_data, bytes):
        csv_data = csv_data.decode("utf-8", errors="replace")

    # classify every line
    parsed_baseline = None
    data_lines = []
    for raw_line in csv_data.splitlines():
        line = raw_line.strip()

        if not line:
            continue
        if line.startswith("#"):
            match = _BASELINE_RE.match(line)
            if match is not None:
                parsed_baseline = int(match.group(1))
            continue
        if line == "END":
            continue
        if line == _HEADER_LINE:
            continue

        data_lines.append(line)

    # parse data eligible lines
    samples = []
    truncated_final_row = False
    malformed_row_count = 0
    last_index = len(data_lines) - 1
    for i, line in enumerate(data_lines):
        sample = _parse_row(line)
        if sample is not None:
            samples.append(sample)
            continue

        if i == last_index:
            truncated_final_row = True
            logger.warning("Dropped truncated final row: %.60r", line)
        else:
            malformed_row_count += 1
            logger.warning("Dropped malformed row %d: %.60r", i, line)

    baseline = gsr_baseline if gsr_baseline is not None else parsed_baseline
    logger.info(
        "Parsed %d samples, malformed %d, truncated_final=%s, baseline=%s" ,
        len(samples), malformed_row_count, truncated_final_row, baseline,
    )

    return ParseResult(
        samples=samples,
        gsr_baseline=baseline,
        truncated_final_row=truncated_final_row,
        malformed_row_count=malformed_row_count,
    )




def _parse_row(line: str) -> dict | None:
    "parse one data line into sample dict or None"
    fields = line.split(",")
    if len(fields) != _EXPECTED_COLS:
        return None
    try:
        return {
            name: convert(value.strip())
            for (name, convert), value in zip(_COLUMNS, fields)
        }
    except ValueError:
        return None
    