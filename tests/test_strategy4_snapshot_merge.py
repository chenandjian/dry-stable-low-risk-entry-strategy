from strategy4.snapshot_merge import merge_leaders, merge_topics


def test_merge_topics_keeps_both_sources_and_warns_when_derived_is_weak():
    live = [{
        "topic_id": "concept:AI算力",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "source": "akshare_ths",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": 92,
        "raw_snapshot": {"source": "live"},
    }]
    derived = [{
        "topic_id": "concept:AI算力",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "source": "historical_kline_derived",
        "status": "NOISE_TOPIC",
        "hot_topic_score": 55,
        "derived_hot_score": 55,
        "topic_index_phase": "WEAK_NOISE",
        "raw_snapshot": {"source": "derived"},
    }]

    merged = merge_topics(live, derived, {"merge_policy": {"block_buyable_on_derived_weak_noise": True}})

    assert len(merged) == 1
    topic = merged[0]
    assert topic["snapshot_source"] == "merged"
    assert topic["source_modes"] == ["live_external", "historical_kline_derived"]
    assert topic["live_hot_score"] == 92
    assert topic["derived_hot_score"] == 55
    assert topic["status"] == "WATCH_HOT"
    assert "derived_weak_noise" in topic["merge_warnings"]


def test_merge_leaders_deduplicates_same_topic_and_code():
    live = [{
        "topic_id": "concept:AI算力",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "source": "akshare_ths",
        "leader_strength_score": 90,
        "tradability_score": 70,
        "raw_snapshot": {"source": "live"},
    }]
    derived = [{
        "topic_id": "concept:AI算力",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "source": "historical_kline_derived",
        "leader_strength_score": 82,
        "tradability_score": 80,
        "membership_mode": "current_members_proxy",
        "raw_snapshot": {"source": "derived", "leader_rs_10d": 0.12},
    }]

    merged = merge_leaders(live, derived)

    assert len(merged) == 1
    leader = merged[0]
    assert leader["snapshot_source"] == "merged"
    assert leader["source_modes"] == ["live_external", "historical_kline_derived"]
    assert leader["live_leader_score"] == 90
    assert leader["derived_leader_score"] == 82
    assert leader["leader_strength_score"] == 90
    assert leader["membership_mode"] == "current_members_proxy"
