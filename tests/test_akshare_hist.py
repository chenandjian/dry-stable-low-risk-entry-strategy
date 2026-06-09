"""测试 akshare 历史行情数据接口。

用法: python tests/test_akshare_hist.py
"""
import time
import traceback


def _retry(func, name, max_retries=3):
    """带重试的 API 调用（东财偶发 ConnectionError）。"""
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries:
                print(f"  {name} attempt {attempt}/{max_retries}: {type(e).__name__}, retrying...")
                time.sleep(3)
            else:
                raise


def test_dongcai():
    """测试东财接口 stock_zh_a_hist"""
    import akshare as ak
    code = "002487"
    print(f"=== 东财 stock_zh_a_hist({code}) ===")

    def _call():
        return ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20200101", end_date="20260609", adjust="qfq",
        )

    df = _retry(_call, "东财")
    print(f"  ✓ {len(df)} rows, cols={list(df.columns)[:6]}")
    print(f"  首行: {dict(df.iloc[0])}")
    print(f"  末行: {dict(df.iloc[-1])}")
    return df


def test_tencent():
    """测试腾讯接口 stock_zh_a_hist_tx"""
    import akshare as ak
    code = "002487"
    print(f"\n=== 腾讯 stock_zh_a_hist_tx({code}) ===")

    def _call():
        return ak.stock_zh_a_hist_tx(
            symbol=code, start_date="20200101", end_date="20260609", adjust="qfq",
        )

    try:
        df = _retry(_call, "腾讯")
        print(f"  ✓ {len(df)} rows, cols={list(df.columns)[:6]}")
        print(f"  首行: {dict(df.iloc[0])}")
        print(f"  末行: {dict(df.iloc[-1])}")
        return df
    except Exception:
        print(f"  ✗ 失败 (akshare bug):")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_dongcai()
    test_tencent()
