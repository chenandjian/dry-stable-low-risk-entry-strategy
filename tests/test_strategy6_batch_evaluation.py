from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import server


def test_strategy6_batch_evaluation_api_validates_codes(monkeypatch):
    called = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"strategy6": {}})
    monkeypatch.setattr(
        server,
        "evaluate_strategy6_batch",
        lambda codes, config: called.append(codes) or {"results": [], "errors": []},
    )
    client = TestClient(server.app)

    response = client.post(
        "/api/strategy6/batch-evaluate",
        json={"codes": ["601857", " 601857 ", "300604"]},
    )

    assert response.status_code == 200
    assert called == [["601857", "300604"]]
    assert response.json()["requestedCount"] == 2

    invalid = client.post(
        "/api/strategy6/batch-evaluate",
        json={"codes": ["601857", "ABC"]},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "INVALID_STOCK_CODES"
    assert invalid.json()["invalidCodes"] == ["ABC"]


def test_strategy6_batch_evaluation_api_rejects_empty_and_oversized_requests(monkeypatch):
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"strategy6": {}})
    client = TestClient(server.app)

    empty = client.post("/api/strategy6/batch-evaluate", json={"codes": []})
    blank = client.post("/api/strategy6/batch-evaluate", json={"codes": ["  "]})
    oversized = client.post(
        "/api/strategy6/batch-evaluate",
        json={"codes": [f"{index:06d}" for index in range(201)]},
    )

    assert empty.status_code == 400
    assert empty.json()["error"] == "EMPTY_STOCK_CODES"
    assert blank.status_code == 400
    assert blank.json()["error"] == "EMPTY_STOCK_CODES"
    assert oversized.status_code == 400
    assert oversized.json()["error"] == "TOO_MANY_STOCK_CODES"


def test_batch_service_uses_local_data_and_prioritizes_tail_score(monkeypatch):
    from strategy6 import batch_evaluator

    rows = [
        {"date": f"2026-01-{day:02d}", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}
        for day in range(1, 25)
    ]
    monkeypatch.setattr(batch_evaluator.db, "get_stock_pool", lambda: [
        {"code": "601857", "name": "中国石油", "market": "sh"},
        {"code": "300604", "name": "长川科技", "market": "sz"},
    ])
    monkeypatch.setattr(
        batch_evaluator.db,
        "get_ohlc",
        lambda code: rows if code in {"601857", "300604"} else None,
    )
    monkeypatch.setattr(batch_evaluator.db, "get_ohlc_metadata", lambda code: {
        "source": "tickflow", "fetched_at": "2026-01-24 15:30:00",
    })
    monkeypatch.setattr(
        batch_evaluator.db,
        "get_market_index_ohlc",
        lambda symbol, **kwargs: rows,
    )

    class FakeEvaluation:
        def __init__(self, code):
            self.code = code
            tail_score = 19 if code == "300604" else 16
            self.dry_tail = SimpleNamespace(
                dry_stable_score=tail_score,
                dry_tail_pass=True,
                tail_volume_ratio=0.55,
                volume_slope_10=-0.02,
                reasons=["volume:non_overlap_tail_dry"],
                rejects=[],
            )
            self.score = SimpleNamespace(
                total_score=90 if code == "601857" else 82,
                tail_score=tail_score,
                strong_start_score=18,
                pattern_score_component=16,
                support_score=17,
                objective_rr_score=8,
                relative_strength_risk_score=5,
                score_reasons=[f"tail={tail_score}"],
            )
            self.indicators = SimpleNamespace(has_big_down_volume=False)
            self.reject_reasons = []

        def to_candidate_dict(self):
            tail_score = 19 if self.code == "300604" else 16
            return {
                "code": self.code,
                "name": "",
                "evaluation_date": "2026-01-24",
                "candidate_type": "WATCH_CANDIDATE",
                "classification": "watch",
                "total_score": 90 if self.code == "601857" else 82,
                "tail_score": tail_score,
                "dry_stable_score": tail_score,
                "original_tail_pass": True,
                "original_tail_score": tail_score,
                "tail_volume_ratio": 0.55,
                "volume_slope_10": -0.02,
                "close_range_5": 0.03,
                "return_5": 0.01,
                "range_5": 0.04,
                "reject_reasons": [],
                "score_reasons": [f"tail={tail_score}"],
            }

    class FakeEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, rows_arg, *, code, **kwargs):
            assert rows_arg is rows
            assert kwargs["market_data_by_symbol"]
            return FakeEvaluation(code)

    monkeypatch.setattr(batch_evaluator, "StrongVcpTailEngine", FakeEngine)

    result = batch_evaluator.evaluate_strategy6_batch(
        ["601857", "000000", "300604"], {"strategy6": {}}
    )

    assert [item["code"] for item in result["results"]] == ["300604", "601857"]
    assert result["results"][0]["tailQualityScore"] == 19
    assert result["results"][0]["tailScore"] == 19
    assert result["results"][0]["tailPass"] is True
    assert result["results"][0]["dataSource"] == "tickflow"
    assert result["errors"] == [{
        "code": "000000", "name": "", "error": "KLINE_NOT_FOUND", "message": "本地没有K线数据",
    }]
