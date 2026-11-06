"""Regression coverage for eleven international, Vietnamese, and hybrid strategy proxy bots."""
import json
import numpy as np
import pandas as pd
from engine import TRADERS, make_features, backtest
from paper_forward import update_paper
from test_engine import data


def test_all_eleven_bots_are_independent_and_valid():
    assert set(TRADERS) == {"Minervini","ONeil","Darvas","BNF","CIS","Qullamaggie","Unger","ThaiPham","DuongChung","PThai","Hybrid"}
    assert {TRADERS[k]["region"] for k in TRADERS} == {"US","JP","EU","VN","MIX"}
    prices, index = data(420)
    features = make_features(prices,index)
    for key in TRADERS:
        assert "buy_"+key in features.columns
        assert features["buy_"+key].dtype == bool
        result = backtest({"FPT": prices}, index, key, "2022-01-03")
        assert np.isfinite(result["nav"]) and result["nav"] > 0
        assert result["trader"] == key
        assert (result["curve"]["nav"] > 0).all()


def test_same_day_upgrade_preserves_existing_paper_and_does_not_backdate(tmp_path):
    prices, benchmark = data(420)
    end = 340
    state_path = tmp_path / "paper_state.json"
    paper, changed = update_paper({"FPT":prices.iloc[:end]},benchmark.iloc[:end],state_path)
    assert changed
    existing = {k:paper["bots"][k].copy() for k in ("Minervini","ONeil","Darvas")}
    for key in ("BNF","CIS","Qullamaggie","Unger"):
        del paper["bots"][key]
    state_path.write_text(json.dumps(paper),encoding="utf-8")
    migrated, changed = update_paper({"FPT":prices.iloc[:end]},benchmark.iloc[:end],state_path)
    assert changed
    assert len(migrated["bots"]) == 11
    for key in ("Minervini","ONeil","Darvas"):
        assert migrated["bots"][key] == existing[key]
    for key in ("BNF","CIS","Qullamaggie","Unger"):
        b=migrated["bots"][key]
        assert b["cash"] == 100_000_000
        assert b["positions"] == {}
        assert b["trades"] == []
        assert len(b["history"]) == 1
        assert b["history"][0]["return_pct"] == 0
    again, changed = update_paper({"FPT":prices.iloc[:end]},benchmark.iloc[:end],state_path)
    assert not changed
    assert again == migrated
