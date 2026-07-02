"""Tests for history.py"""
"""
tmp_path is a built-in pytest fixture.
Declaring tmp_path as a parameter makes pytest hand each test its own brand-new 
temporary directory!!!
"""

from ssb_backend.history import(
    MAX_SESSIONS,
    get_recent_sessions,
    get_session_count,
    init_db,
    save_session,
)

# helpers ---------------------------------------------------------------------
def _save_n(db, n, start=0):
    """Save n sessions"""
    for i in range(start, start + n):
        save_session(
            {"session": i},
            db_path=db,
            timestamp=f"2026-07-02T00:00:{i:02d}",
        )

def _session_indices(db, **kwargs):
    return [s["session"] for s in get_recent_sessions(db_path=db, **kwargs)]



# tests -----------------------------------------------------------------------
def test_fresh_db_count_zero(tmp_path):
    db = tmp_path / "ssb_history.db"

    assert get_session_count(db_path=db) == 0


def test_save_and_retrieve_roundtrip(tmp_path):
    db = tmp_path / "ssb_history.db"
    result = {"score": 87.5, "rehydration": {"fluid_ml": 750, "sodium_mg": 900}}

    save_session(result, db_path=db, timestamp="2026-07-02T00:00:00")

    assert get_recent_sessions(db_path=db) == [result]


def test_ordering_oldest_to_newest(tmp_path):
    db = tmp_path / "ssb_history.db"
    _save_n(db, 3)

    assert _session_indices(db) == [0, 1, 2]


def test_sliding_window_eviction(tmp_path):
    db = tmp_path / "ssb_history.db"
    _save_n(db, 7)  # 0 and 1 should be evicted

    assert get_session_count(db_path=db) == MAX_SESSIONS
    assert _session_indices(db) == [2, 3, 4, 5, 6]


def test_limit_parameter(tmp_path):
    db = tmp_path / "ssb_history.db"
    _save_n(db, 5)

    assert _session_indices(db, limit=2) == [3, 4]


def test_init_db_idempotent(tmp_path):
    db = tmp_path / "ssb_history.db"

    init_db(db)
    init_db(db)  # second call must not raise or corrupt

    _save_n(db, 1)
    assert get_session_count(db_path=db) == 1