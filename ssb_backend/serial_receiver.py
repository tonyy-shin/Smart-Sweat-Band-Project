"""
USB serial receiver for the SSB backend.

Pulls data from the XIAO ESP32S3.
backend -> 'R'
device -> <csv line>
device -> "END"
backend -> 'C'

'C' is sent after the END sentinel was received, and the CSV is saved to disk.
Only a broken stream withholds 'C', so the device keeps the file for a retry 
on the next connection.
"""

from __future__ import annotations

from datetime import datetime
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import serial
import serial.tools.list_ports

from ssb_backend.parser import ParseResult, parse_session_csv

import logging
logger = logging.getLogger(__name__)

# Config Constants ---------------------------------------------------------------
BAND_RATE = 115200
REQUEST_BYTE = b'R'
CONFIRM_BYTE = b'C'
END_SENTINEL = "END"
ERROR_PREFIX = "ERROR"
EXPECTED_COLS = 5
READ_TIMEOUT_S = 2.0
POLL_INTERVAL_S = 2.0
REPROBE_COOLDOWN_CYCLES = 15
DATA_DIR = Path(__file__).resolve().parent / "data"
_HEADER_LINE = "timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw"



# Result Type -----------------------------------------------------------------------
@dataclass
class ReceiveResult:
    csv_text: str
    complete: bool
    device_reported_error: bool

@dataclass
class TransferOutcome:
    detected: bool
    complete: bool
    confirmed: bool
    saved_path: Path | None
    parse_result: ParseResult | None




# Pure Core Functions --------------------------------------------------------------------------------
def _looks_like_ssb(line: str) -> bool:
    """
    Check if a line looks like a valid SSB CSV line. 
    Filters out random serial junk for the device.
    """
    return (
        line.startswith("#gsr_baseline")
        or line == _HEADER_LINE
        or len(line.split(",")) == EXPECTED_COLS
    )


def accumulate_stream(lines: Iterable[str]) -> ReceiveResult:
    """
    Consume decoded lines until END / ERROR / exhaustion.
    """
    collected: list[str] = []
    complete = False
    device_error = False
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == END_SENTINEL:
            complete = True
            break
        if line.startswith(ERROR_PREFIX):
            device_error = True
            break
        collected.append(line)
    
    csv_text = "\n".join(collected)
    if collected:
        csv_text += "\n"
    return ReceiveResult(
        csv_text=csv_text,
        complete=complete,
        device_reported_error=device_error,
    )




# Save --------------------------------------------------------------------------------
def save_csv(
        csv_text: str, data_dir: Path = DATA_DIR, *, timestamp: str | None = None
        ) -> Path:
    """
    Write csv_text to data_dir and fsync it to disk
    
    fsync must be complete before 'C' is sent.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = data_dir / f"session_{ts}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
        f.flush()
        os.fsync(f.fileno())
    return path




# Serial IO + orchestration ------------------------------------------------------------------------
def _read_line(ser) -> Iterator[str]:
    """
    Yield lines from serial until it stalls.

    returns:
        b"" on timeout.
    """
    while True:
        raw = ser.readline()
        if not raw:
            return
        yield raw.decode("utf-8", errors="replace")


def _process_connection(ser) -> TransferOutcome | None:
    """
    Run the full R -> <csv> -> END -> C sequence.

    Returns:
        None if port does not behave like SSB device.
        TransferOutcome if the device was detected.
    """
    ser.reset_input_buffer()
    ser.write(REQUEST_BYTE)
    ser.flush()

    recv = accumulate_stream(_read_line(ser))

    first = recv.csv_text.splitlines()[0] if recv.csv_text else ""
    detected = (
        recv.complete
        or recv.device_reported_error
        or (bool(first) and _looks_like_ssb(first))
    )
    if not detected:
        return None
    
    if recv.device_reported_error:
        logger.info("Device reports no session to transfer")
        return TransferOutcome(True, False, False, None, None)
    
    saved_path = None
    confirmed = False
    if recv.complete:
        saved_path = save_csv(recv.csv_text)
        ser.write(CONFIRM_BYTE)
        ser.flush()
        confirmed = True
        logger.info("Full transfer received; saved to %s and sent confirmation"
                    , saved_path)
    else:
        logger.warning("Incomplete transfer received; not saving or confirming")

    parse_result = parse_session_csv(recv.csv_text) if recv.csv_text else None
    if (parse_result is not None):
        _log_parse_health(parse_result)

    return TransferOutcome(True, recv.complete, confirmed, saved_path, parse_result)


def _log_parse_health(pr: ParseResult) -> None:
    """
    Log the two parser failure fields distinctly

    truncated_final_rw -> expected power pull, which results in a loss of data at the end of the session.
    malformed_row_count -> real mid session corruption (We no likey)
    """
    logger.info("Parsed %d samples (basline-%s)", len(pr.samples), pr.gsr_baseline)
    if pr.truncated_final_row:
        logger.info("Final row truncated - expected on mid recording power pull; tolerated")
    if pr.malformed_row_count:
        logger.warning(
            "Dropped %d malformed rows - possible mid session corruption",
            pr.malformed_row_count,
        )




# Detection Scan + Transfer Loop ---------------------------------------------------------------------------
def list_candidate_ports() -> list[str]:
    """
    List all serial ports that could be the SSB device.
    """
    return [p.device for p in serial.tools.list_ports.comports()]


def try_port(port: str) -> TransferOutcome | None:
    """
    Attempt to connect to a port and transfer.

    Returns:
        None if the port does not behave like the SSB device.
    """
    try:
        with serial.Serial(port, BAND_RATE, timeout=READ_TIMEOUT_S) as ser:
            return _process_connection(ser)
    except (serial.SerialException, OSError) as e:
        logger.debug("Port %s not usable: %s", port, e)
        return None
    

def run(poll_interval_s: float = POLL_INTERVAL_S) -> None:
    """
    Scan for SSB and transfer when it appears.

    Active probing sends 'R' to ports.
    Non responders go on temporary cooldown. 
    Cooldown ensures re probing is not too aggressive.
    """
    ssb_port: str | None = None
    cooldown: dict[str, int] = dict()
    logger.info("SSB serial receiver started; scanning for devices...")

    while True:
        try:
            ports = set(list_candidate_ports())
            cooldown = {p: c for p, c in cooldown.items() if p in ports} # drop unplugged ports
            if ssb_port not in ports:
                ssb_port = None
            for p in list(cooldown):
                cooldown[p] -= 1
                if cooldown[p] <= 0:
                    del cooldown[p]

            # re poll known SSB ports every cycle
            candidates = ([ssb_port] if ssb_port else []) + \
                         [p for p in ports if p != ssb_port and p not in cooldown]
            for port in candidates:
                outcome = try_port(port)
                if outcome is None:
                    if port != ssb_port:
                        cooldown[port] = REPROBE_COOLDOWN_CYCLES
                    continue
                ssb_port = port
                if outcome.saved_path is not None:
                    _run_algorithm_pipeline(outcome)
        except Exception:
            logger.exception("Error during scan/receive cycle")
        time.sleep(poll_interval_s)

            
def _run_algorithm_pipeline(outcome: TransferOutcome) -> None:
    # TODO: invoke ssb_backend.algorithm once algorithm is written.
    n = len(outcome.parse_result.samples) if outcome.parse_result else 0
    logger.info("TODO: run algorithm on %d samples", n)




if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()