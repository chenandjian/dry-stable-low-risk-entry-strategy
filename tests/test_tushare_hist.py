"""测试 tushare 日线行情数据接口。

用法: python tests/test_tushare_hist.py
依赖: pip install tushare

结果:
- pro.daily(): 需要付费 token (权限不足)
- get_hist_data(): 旧接口已下线 (DNS 解析失败)
"""
import sys
import traceback

CODE = "002487"
TOKEN = "c3ac2c577fbd814d72508e7f647f0c259ad94c210ac44ae92fd0cffb"


def test_pro_daily():
    """测试 tushare pro 接口 (需要付费权限)"""
    import tushare as ts
    print(f"=== tushare pro.daily({CODE}) ===")
    print(f"   tushare: {ts.__version__}")
    ts.set_token(TOKEN)
    pro = ts.pro_api()
    try:
        df = pro.daily(ts_code=f"{CODE}.SZ", start_date="20200101", end_date="20260609")
        print(f"   ✓ {len(df)} rows, cols={list(df.columns)[:6]}")
        return df
    except Exception as e:
        print(f"   ✗ {e}")
        return None


def test_old_api():
    """测试 tushare 旧版接口 (已下线)"""
    import tushare as ts
    print(f"\n=== tushare get_hist_data({CODE}) ===")
    ts.set_token(TOKEN)
    try:
        df = ts.get_hist_data(CODE, start="2020-01-01", end="2026-06-09")
        if df is not None and len(df) > 0:
            print(f"   ✓ {len(df)} rows, cols={list(df.columns)[:6]}")
            return df
        print("   ✗ 返回空数据")
    except Exception as e:
        print(f"   ✗ {e}")
    return None


if __name__ == "__main__":
    test_pro_daily()
    test_old_api()
