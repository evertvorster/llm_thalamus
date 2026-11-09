"""Tests for src/controller/hindsight_cost.py — pure, no Qt, no network."""

from __future__ import annotations

import subprocess

import pytest

from controller import hindsight_cost as hc
from controller.hindsight_cost import Spend


def row(model="deepseek-v4-flash", input_tokens=1000, cached_tokens=400,
        output_tokens=100, thoughts_tokens=50, operation="retain"):
    return {
        "model": model,
        "operation": operation,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "thoughts_tokens": thoughts_tokens,
    }


class TestSpend:
    def test_cost_prices_uncached_cached_and_output_separately(self):
        # 1000 in of which 400 cached, 100 out, 50 thoughts: the reasoning is
        # billed as output, which is why it is added to it.
        spend = Spend(calls=1, input=1000, cached=400, output=100, thoughts=50)
        expected = (600 * 0.30 + 400 * 0.006 + 150 * 1.20) / 1e6
        assert spend.cost == pytest.approx(expected)

    def test_cached_never_exceeds_input_in_cost(self):
        # A provider reporting more cached than prompt tokens must not make the
        # uncached term negative.
        spend = Spend(calls=1, input=10, cached=500, output=0, thoughts=0)
        assert spend.cost == pytest.approx(500 * 0.006 / 1e6)

    def test_cache_rate(self):
        assert Spend(input=1000, cached=250).cache_rate == pytest.approx(0.25)
        assert Spend().cache_rate is None

    def test_main_repo_uses_the_repo_name(self, tmp_path):
        repo = tmp_path / "myproject"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        assert hc.bank_for(repo) == "coding-agent::myproject"
        # A subdirectory belongs to the same bank.
        (repo / "src").mkdir()
        assert hc.bank_for(repo / "src") == "coding-agent::myproject"

    def test_worktree_shares_the_main_repo_bank(self, tmp_path):
        repo = tmp_path / "myproject"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                        "-m", "x"], check=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": "/usr/bin:/bin"})
        tree = tmp_path / "wt"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q",
                        str(tree), "-b", "side"], check=True)
        assert hc.bank_for(tree) == "coding-agent::myproject"

    def test_plain_directory_uses_its_own_name(self, tmp_path):
        plain = tmp_path / "notarepo"
        plain.mkdir()
        assert hc.bank_for(plain) == "coding-agent::notarepo"


class TestSpendFor:
    def test_skips_rows_without_a_model(self, monkeypatch):
        # Embedding calls run locally and carry null tokens; counting them
        # would inflate the call count and add nothing.
        page = {"total": 3, "items": [
            row(),
            {"model": "", "provider": "onnx", "input_tokens": None},
            row(input_tokens=2000, cached_tokens=0, output_tokens=0,
                thoughts_tokens=0),
        ]}
        monkeypatch.setattr(hc, "_get", lambda path: page)
        spend = hc.spend_for("coding-agent::x")
        assert spend.calls == 2
        assert spend.input == 3000

    def test_pages_until_total_is_reached(self, monkeypatch):
        pages = {
            0: {"total": 3, "items": [row(), row()]},
            2: {"total": 3, "items": [row()]},
        }
        monkeypatch.setattr(hc, "_get", lambda path: pages.get(
            int(path.rsplit("offset=", 1)[1])))
        assert hc.spend_for("coding-agent::x").calls == 3

    def test_unreachable_api_is_an_empty_spend(self, monkeypatch):
        monkeypatch.setattr(hc, "_get", lambda path: None)
        assert hc.spend_for("coding-agent::x").calls == 0

    def test_document_filter_is_quoted_into_the_path(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(hc, "_get", lambda path: seen.setdefault("p", path) and None)
        hc.spend_for("coding-agent::x",
                     document_id="conversation:01a1c14f-1afc-7676-8108-9c9f1127e9e0")
        assert "document_id=conversation%3A01a1c14f" in seen["p"]

    def test_groups_and_skips_embedding_rows(self, monkeypatch):
        page = {"total": 4, "items": [
            row(operation="retain"),
            row(operation="consolidation", input_tokens=5000, cached_tokens=1000),
            row(operation="retain"),
            {"model": "", "operation": "retain", "input_tokens": None},
        ]}
        monkeypatch.setattr(hc, "_get", lambda path: page)
        by_op = hc.spend_by_operation("coding-agent::x")
        assert by_op["retain"].calls == 2
        assert by_op["consolidation"].input == 5000
        assert set(by_op) == {"retain", "consolidation"}
