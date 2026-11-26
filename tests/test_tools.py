import pytest

from forgeai.tools.calculator import calculate
from forgeai.tools.registry import TOOLS, run_tool


def test_calculator_arithmetic():
    assert calculate("12 * 45.5") == 546
    assert calculate("1,200 * (1 - 5%)") == 1140
    assert calculate("3 x 4") == 12
    assert calculate("round(10/3, 2)") == 3.33
    assert calculate("max(2, 7) + min(1, 5)") == 8


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "().__class__.__bases__",
    "open('x')",
    "a + 1",
    "lambda: 1",
    "9 ** 99999",
])
def test_calculator_rejects_unsafe(expr):
    with pytest.raises((ValueError, SyntaxError)):
        calculate(expr)


def test_only_attached_tools_can_run():
    out, ok = run_tool("calculator", {"expression": "1+1"}, {}, allowed=["current_date"])
    assert not ok and "not available" in out
    out, ok = run_tool("calculator", {"expression": "1+1"}, {}, allowed=["calculator"])
    assert ok and out.endswith("2")


def test_registry_has_four_tools_with_guidance():
    assert set(TOOLS) == {"csv_lookup", "calculator", "weather", "current_date"}
    for spec in TOOLS.values():
        assert spec.when_to_use and spec.when_not_to_use


def test_csv_lookup(tmp_path):
    (tmp_path / "items.csv").write_text("part_no,price\nAB-1,10\nAB-2,25\n", encoding="utf-8")
    out, ok = run_tool("csv_lookup", {"file": "items.csv", "column": "part_no", "value": "ab-2"},
                       {"documents_dir": str(tmp_path)}, ["csv_lookup"])
    assert ok and "price: 25" in out
    out, _ = run_tool("csv_lookup", {"column": "pric", "value": "15", "match": "gt"},
                      {"documents_dir": str(tmp_path)}, ["csv_lookup"])
    assert "AB-2" in out and "AB-1" not in out
