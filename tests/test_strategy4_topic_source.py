import sys
import types

from strategy4.topic_source import TopicSourceService


def test_topic_source_reads_akshare_ths_concept_and_industry(monkeypatch):
    fake_ak = types.SimpleNamespace()

    def concept():
        return _fake_frame([
            {"板块": "AI算力", "涨跌幅": 4.5, "总成交额": 1800000000, "净流入": 500000000, "上涨家数": 78, "下跌家数": 12, "领涨股票": "宁德时代"},
        ])

    def industry():
        return _fake_frame([
            {"板块": "半导体", "涨跌幅": 3.2, "总成交额": 1200000000, "净流入": 200000000, "上涨家数": 60, "下跌家数": 20, "领涨股票": "中芯国际"},
        ])

    fake_ak.stock_board_concept_name_ths = concept
    fake_ak.stock_board_industry_name_ths = industry
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    topics = TopicSourceService().fetch_topics()

    assert {t["topic_name"] for t in topics} == {"AI算力", "半导体"}
    assert topics[0]["source"] == "akshare_ths"
    assert topics[0]["return_1d"] == 0.045
    assert topics[0]["breadth_ratio"] > 0.8


def test_topic_source_handles_ths_name_code_rows_without_default_names(monkeypatch):
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([
        {"name": "AI PC", "code": "309121"},
    ])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([
        {"name": "半导体", "code": "881121"},
    ])
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    topics = TopicSourceService().fetch_topics()

    assert topics[0]["topic_name"] == "AI PC"
    assert topics[0]["topic_id"] == "concept:AI PC"
    assert topics[0]["raw_snapshot"] == {"name": "AI PC", "code": "309121"}
    assert topics[1]["topic_name"] == "半导体"


def test_topic_source_prefers_ths_summary_rows_for_scored_topics(monkeypatch):
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_summary_ths = lambda: _fake_frame([])
    fake_ak.stock_board_industry_summary_ths = lambda: _fake_frame([
        {
            "板块": "保险",
            "涨跌幅": 6.89,
            "总成交额": 175.8,
            "净流入": 32.76,
            "上涨家数": 5,
            "下跌家数": 0,
            "领涨股": "新华保险",
            "领涨股-涨跌幅": 9.81,
        },
    ])
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    topics = TopicSourceService().fetch_topics()

    assert topics[0]["topic_name"] == "保险"
    assert topics[0]["return_1d"] == 0.0689
    assert topics[0]["amount_ratio"] > 1.0
    assert topics[0]["net_inflow"] > 3_000_000_000
    assert topics[0]["breadth_ratio"] == 1.0
    assert topics[0]["leading_stock_name"] == "新华保险"


def test_topic_source_reads_ths_topic_members(monkeypatch):
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
        {"代码": "688981", "名称": "中芯国际", "涨跌幅": 12.0, "成交额": 1500000000},
    ])
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    members = TopicSourceService().fetch_topic_members("AI算力", "concept")

    assert [m["code"] for m in members] == ["300750", "688981"]
    assert members[0]["return_1d"] == 0.20
    assert members[0]["amount"] == 2000000000


class _fake_frame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._rows)
