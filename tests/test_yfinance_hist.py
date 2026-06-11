"""测试 yfinance 日线行情数据接口。

用法: python tests/test_yfinance_hist.py
依赖: pip install yfinance

yfinance 免费、无需注册、支持 A 股(SSE: .SS / SZSE: .SZ)。
"""
import sys

CODE = "002487"


def test_yfinance_daily():
    """测试 yfinance 获取 A 股日线"""
    import yfinance as yf

    sym = f"{CODE}.SZ"
    print(f"=== yfinance Ticker({sym}) ===")
    print(f"   yfinance: {yf.__version__}")

    ticker = yf.Ticker(sym)
    df = ticker.history(start="2020-01-01", end="2026-06-09")

    assert len(df) > 0, "yfinance 返回空数据"
    print(f"   ✓ {len(df)} rows")
    print(f"   列: {list(df.columns)}")

    # yfinance 返回 auto-adjusted 价格
    row0 = df.iloc[0]
    rown = df.iloc[-1]
    print(f"   首行: date={df.index[0].date()} O={row0['Open']:.2f} H={row0['High']:.2f} L={row0['Low']:.2f} C={row0['Close']:.2f} V={int(row0['Volume'])}")
    print(f"   末行: date={df.index[-1].date()} O={rown['Open']:.2f} H={rown['High']:.2f} L={rown['Low']:.2f} C={rown['Close']:.2f} V={int(rown['Volume'])}")

    assert "Open" in df.columns
    assert "Close" in df.columns
    assert "Volume" in df.columns
    print("   ✓ 通过 (免费、无需token、已前复权)")
    return df


if __name__ == "__main__":
    test_yfinance_daily()
