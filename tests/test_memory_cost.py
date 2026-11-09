"""Tests for src/controller/memory_cost.py — reads another process's database."""

from __future__ import annotations

import sqlite3

import pytest

from controller import memory_cost as mc

SCHEMA = """
create table turns(id integer primary key, session_id text, ts text,
                   tag_in_tok integer, tag_out_tok integer, tag_cost real);
"""


def make_db(tmp_path, rows):
    path = tmp_path / "memory.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("insert into turns(session_id, ts, tag_in_tok, tag_out_tok, "
                    "tag_cost) values(?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


class TestSessionUuid:
    def test_reads_the_uuid_after_the_timestamp(self):
        name = ("/s/--proj--/2026-11-09T17-15-49-372Z_"
                "01a1c14f-1afc-7676-8108-9c9f1127e9e0.jsonl")
        assert mc.session_uuid(name) == "01a1c14f-1afc-7676-8108-9c9f1127e9e0"

    def test_missing_path_is_none(self):
        assert mc.session_uuid(None) is None
        assert mc.session_uuid("") is None


class TestSessionTagSpend:
    def test_sums_only_the_tagged_turns_of_that_session(self, tmp_path):
        db = make_db(tmp_path, [
            ("s1", "2026-11-09T20:00:00Z", 1000, 50, 0.0004),
            ("s1", "2026-11-09T20:01:00Z", 900, 40, 0.0003),
            ("s2", "2026-11-09T20:02:00Z", 900, 40, 0.0009),
            ("s1", "2026-11-09T20:03:00Z", None, None, None),   # not tagged
        ])
        assert mc.session_tag_spend("s1", db) == (2, pytest.approx(0.0007))

    def test_untagged_session_reports_nothing(self, tmp_path):
        db = make_db(tmp_path, [("s1", "2026-11-09T20:00:00Z", None, None, None)])
        assert mc.session_tag_spend("s1", db) is None

    def test_absent_database_reports_nothing(self, tmp_path):
        assert mc.session_tag_spend("s1", tmp_path / "nope.db") is None

    def test_no_session_id_reports_nothing(self, tmp_path):
        db = make_db(tmp_path, [("s1", "2026-11-09T20:00:00Z", 10, 2, 0.1)])
        assert mc.session_tag_spend(None, db) is None

    def test_a_corrupt_database_is_not_fatal(self, tmp_path):
        path = tmp_path / "memory.db"
        path.write_text("this is not sqlite")
        assert mc.session_tag_spend("s1", path) is None
