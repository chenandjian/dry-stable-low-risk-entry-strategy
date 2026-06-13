# tests/test_strategy2_independence.py
"""策略2独立性边界检查 — strategy2/ 不得导入策略1判断模块。"""
import ast
import os
import sys


STRATEGY2_DIR = os.path.join(os.path.dirname(__file__), "..", "strategy2")

# 策略1判断模块 — strategy2 禁止导入
FORBIDDEN_MODULES = {
    "scanner.pattern_detector",
    "scanner.strategy_engine",
    "scanner.scorer",
    "analyzer.dry_stable",
    "analyzer.volume_dry",
    "analyzer.price_stable",
    "analyzer.pattern_score",
    "analyzer.decision",
    "analyzer.key_prices",
    "analyzer.risk_reward",
    "analyzer.invalid_rules",
    "analyzer.market_env",
}

# strategy2 允许导入的共享基础设施模块
ALLOWED_IMPORTS = {
    "strategy2",
    "strategy2.models",
    "strategy2.indicators",
    "strategy2.scorer",
    "strategy2.rejection",
    "strategy2.risk",
    "strategy2.engine",
    "strategy2.scanner",
    "logging",
    "json",
    "datetime",
    "time",
    "threading",
    "queue",
    "collections",
    "typing",
    "dataclasses",
    "math",
    "statistics",
    "hashlib",
    "itertools",
    "functools",
    "os",
    "sys",
    "traceback",
    "abc",
    "copy",
}


def _get_imports(filepath: str) -> list[str]:
    """Extract all import module names from a Python file."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _strategy2_files():
    """Yield all .py files in strategy2/. """
    for root, dirs, files in os.walk(STRATEGY2_DIR):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


class TestStrategy2Independence:
    def test_no_forbidden_imports(self):
        """strategy2/ 不得导入策略1判断模块。"""
        violations = []
        for filepath in _strategy2_files():
            imports = _get_imports(filepath)
            for imp in imports:
                if imp in FORBIDDEN_MODULES:
                    violations.append(f"{os.path.basename(filepath)} imports {imp}")
                # Also check sub-imports
                for forbidden in FORBIDDEN_MODULES:
                    if imp.startswith(forbidden + "."):
                        violations.append(f"{os.path.basename(filepath)} imports {imp}")

        if violations:
            pytest.fail(
                "strategy2/ files must not import strategy1 modules:\n  "
                + "\n  ".join(violations)
            )

    def test_no_scanner_engine_import_from_strategy2(self):
        """Specifically verify no strategy2 file imports scanner.engine."""
        for filepath in _strategy2_files():
            imports = _get_imports(filepath)
            assert "scanner.engine" not in imports, \
                f"{os.path.basename(filepath)} imports scanner.engine"

    def test_no_analyzer_import_from_strategy2(self):
        """Specifically verify no strategy2 file imports any analyzer.* module."""
        for filepath in _strategy2_files():
            imports = _get_imports(filepath)
            for imp in imports:
                assert not imp.startswith("analyzer."), \
                    f"{os.path.basename(filepath)} imports {imp}"

    def test_strategy2_modules_exist(self):
        """All 10 strategy2 modules should exist."""
        expected = [
            "__init__.py",
            "models.py",
            "indicators.py",
            "scorer.py",
            "rejection.py",
            "risk.py",
            "engine.py",
            "trend.py",
            "backtest_models.py",
            "backtester.py",
        ]
        for f in expected:
            path = os.path.join(STRATEGY2_DIR, f)
            assert os.path.exists(path), f"Missing: {f}"

    def test_strategy2_public_api(self):
        """Core functions should be importable from strategy2 modules."""
        from strategy2.models import Strategy2Evaluation, Strategy2Indicators, Strategy2Score
        from strategy2.indicators import compute_indicators, validate_strategy_data
        from strategy2.scorer import compute_total_score
        from strategy2.rejection import check_rejection_rules
        from strategy2.risk import compute_key_support, compute_risk
        from strategy2.engine import ExtremeDryStableStrategyEngine
        # If we get here, all imports work
        assert True
