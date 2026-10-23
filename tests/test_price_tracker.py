"""Tests for price_tracker. Run with: python -m pytest tests/ -v"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from price_tracker import (  # noqa: E402
    compare_snapshots,
    format_change,
    load_snapshot,
    parse_price,
    parse_products,
    run_once,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
V1 = (PROJECT_DIR / "sample_data" / "sample_page_v1.html").read_text(encoding="utf-8")
V2 = (PROJECT_DIR / "sample_data" / "sample_page_v2.html").read_text(encoding="utf-8")


def test_parse_products_v1():
    products = parse_products(V1, base_url="https://technest.example")
    assert len(products) == 4
    by_name = {p["name"]: p for p in products}
    assert by_name["Aurora Wireless Headphones"]["price"] == 129.99
    assert by_name["MechType Mechanical Keyboard K87"]["price"] == 89.50
    assert by_name["ErgoFlex Laptop Stand"]["url"] == (
        "https://technest.example/products/ergoflex-laptop-stand"
    )


def test_parse_price_formats():
    assert parse_price("$1,299.99") == 1299.99
    assert parse_price("1.299,99 €") == 1299.99
    assert parse_price("49,99") == 49.99
    assert parse_price("$34.99") == 34.99


def test_compare_snapshots_detects_all_change_types():
    old = {"A": 100.0, "B": 50.0, "C": 20.0}
    new = {"A": 80.0, "B": 60.0, "D": 10.0}
    changes = {c["name"]: c for c in compare_snapshots(old, new)}
    assert changes["A"]["type"] == "drop" and changes["A"]["pct"] == -20.0
    assert changes["B"]["type"] == "rise"
    assert changes["C"]["type"] == "removed"
    assert changes["D"]["type"] == "new"
    assert "PRICE DROP" in format_change(changes["A"])


def test_run_once_end_to_end(tmp_path):
    first = run_once(V1, tmp_path)
    assert first["count"] == 4 and first["changes"] == []
    assert first["snapshot"].exists()

    second = run_once(V2, tmp_path)
    kinds = {c["name"]: c["type"] for c in second["changes"]}
    assert kinds == {
        "Aurora Wireless Headphones": "drop",
        "ClearView 27-inch Monitor Arm": "new",
        "ErgoFlex Laptop Stand": "removed",
        "MechType Mechanical Keyboard K87": "rise",
    }

    log = (tmp_path / "price_changes.log").read_text(encoding="utf-8")
    assert "PRICE DROP: Aurora Wireless Headphones 129.99 -> 99.99" in log
    assert load_snapshot(second["snapshot"])["VoltEdge 65W USB-C Charger"] == 34.99
