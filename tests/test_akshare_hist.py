"""测试 akshare 历史行情数据接口。

用法: python tests/test_akshare_hist.py
"""
import sys
import traceback


def test_dongcai():
    """测试东财接口 stock_zh_a_hist"""
    import akshare as ak
    code = "002487"
    print(f"=== 东财 stock_zh_a_hist({code}) ===")
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date="20200101",
        end_date="20260609",
        adjust="qfq",
    )
    assert len(df) > 0, "东财返回空数据"
    print(f"  行数: {len(df)}")
    print(f"  列: {list(df.columns)}")
    print(f"  首行: {df.iloc[0].to_dict()}")
    print(f"  末行: {df.iloc[-1].to_dict()}")
    assert "日期" in df.columns
    assert "开盘" in df.columns
    assert "收盘" in df.columns
    assert "成交量" in df.columns
    print("  ✓ 通过")
    return df


def test_tencent():
    """测试腾讯接口 stock_zh_a_hist_tx"""
    import akshare as ak
    code = "002487"
    print(f"\n=== 腾讯 stock_zh_a_hist_tx({code}) ===")
    try:
        df = ak.stock_zh_a_hist_tx(
            symbol=code,
            start_date="20200101",
            end_date="20260609",
            adjust="qfq",
        )
        assert len(df) > 0, "腾讯返回空数据"
        print(f"  行数: {len(df)}")
        print(f"  列: {list(df.columns)}")
        print(f"  首行: {df.iloc[0].to_dict()}")
        print(f"  末行: {df.iloc[-1].to_dict()}")
        print("  ✓ 通过")
        return df
    except Exception:
        print(f"  ✗ 失败 (akshare 1.16.44 已知bug):")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_dongcai()
    test_tencent()
