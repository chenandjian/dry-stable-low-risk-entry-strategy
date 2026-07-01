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
