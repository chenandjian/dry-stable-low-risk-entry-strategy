import json

import scanner.tencent_source as tencent_source


class _Response:
    def __init__(self, payload: dict):
        self.text = "kline_day=" + json.dumps(payload)

    def raise_for_status(self):
        return None


def _payload(symbol: str, rows: list[list[str]], quote: list[str]) -> dict:
    return {
        "code": 0,
        "data": {
            symbol: {
                "qfqday": rows,
                "qt": {symbol: quote},
            }
        },
    }


def _quote(*, code: str, date: str, volume: str, amount_wan: str) -> list[str]:
    values = [""] * 88
    values[2] = code
    values[6] = volume
    values[30] = date.replace("-", "") + "161500"
    values[57] = amount_wan
    return values


def test_tencent_converts_lot_volume_to_shares_for_main_board(monkeypatch):
    symbol = "sh600519"
    payload = _payload(
        symbol,
        [
            ["2026-07-20", "1270.00", "1327.50", "1329.00", "1266.00", "106151"],
            ["2026-07-21", "1338.98", "1308.00", "1344.70", "1296.87", "77148"],
        ],
        _quote(
            code="600519",
            date="2026-07-21",
            volume="77148",
            amount_wan="1017430.4108",
        ),
    )
    monkeypatch.setattr(tencent_source.requests, "get", lambda *args, **kwargs: _Response(payload))

    rows = tencent_source.fetch_tencent_daily("600519", 2)

    assert rows is not None
    assert rows[0]["volume"] == 10_615_100
    assert rows[1]["volume"] == 7_714_800
    assert rows[1]["turnover"] == 10_174_304_108


def test_tencent_keeps_share_volume_for_star_market(monkeypatch):
    symbol = "sh688981"
    payload = _payload(
        symbol,
        [
            ["2026-07-20", "145.00", "144.00", "147.47", "138.11", "93942500"],
            ["2026-07-21", "148.00", "160.00", "161.40", "140.58", "113980756"],
        ],
        _quote(
            code="688981",
            date="2026-07-21",
            volume="113980756",
            amount_wan="1726506.4638",
        ),
    )
    monkeypatch.setattr(tencent_source.requests, "get", lambda *args, **kwargs: _Response(payload))

    rows = tencent_source.fetch_tencent_daily("688981", 2)

    assert rows is not None
    assert rows[0]["volume"] == 93_942_500
    assert rows[1]["volume"] == 113_980_756
    assert rows[1]["turnover"] == 17_265_064_638


def test_tencent_rejects_response_when_volume_unit_cannot_be_inferred(monkeypatch):
    symbol = "sh688981"
    payload = _payload(
        symbol,
        [["2026-07-21", "148.00", "160.00", "161.40", "140.58", "113980756"]],
        _quote(code="688981", date="2026-07-21", volume="113980756", amount_wan=""),
    )
    monkeypatch.setattr(tencent_source.requests, "get", lambda *args, **kwargs: _Response(payload))

    assert tencent_source.fetch_tencent_daily("688981", 1) is None
