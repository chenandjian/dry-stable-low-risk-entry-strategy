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
}


def test_strategy3_does_not_import_strategy1_or_strategy2_decision_modules():
    for path in Path("strategy3").glob("*.py"):
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

