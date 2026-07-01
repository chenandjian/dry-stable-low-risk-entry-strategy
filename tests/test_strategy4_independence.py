import ast
from pathlib import Path


FORBIDDEN_IMPORTS = {
    "scanner.pattern_detector",
    "scanner.strategy_engine",
    "analyzer",
    "strategy2.engine",
    "strategy2.scorer",
    "strategy2.rejection",
    "strategy2.trend",
    "strategy3.engine",
    "strategy3.scorer",
    "strategy3.trade_quality",
}


def test_strategy4_does_not_import_strategy1_2_3_decision_modules():
    for path in Path("strategy4").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not any(
                    name == forbidden or name.startswith(forbidden + ".")
                    for forbidden in FORBIDDEN_IMPORTS
                ), (str(path), name)
