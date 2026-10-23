#!/usr/bin/env python3
"""
price_tracker.py - Track product prices on an e-commerce listing page.

What it does
------------
* Parses product cards (name, price, link) from HTML with BeautifulSoup.
* Works online (fetch a URL with ``requests``) or fully offline
  (parse a local HTML file), so the bundled demo needs no network.
* Saves every run as a timestamped CSV snapshot.
* Compares the newest snapshot against the previous one and appends
  price changes to ``price_changes.log``.

Usage
-----
    python price_tracker.py --demo                      # offline demo
    python price_tracker.py --source page.html          # local HTML file
    python price_tracker.py --url "https://shop.example.com/laptops"

When scraping a real shop, respect its Terms of Service and robots.txt,
and adapt the CSS selectors in SELECTORS to the site's markup.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# CSS selectors for one product card. Adjust to match the target site.
SELECTORS = {
    "card": "div.product-card",
    "name": ".product-name",
    "price": ".product-price",
    "link": "a.product-link",
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_price(text: str) -> float:
    """Turn a price string like '$1,299.99' or '1.299,99 EUR' into a float.

    Heuristic: keep digits, '.' and ','; if both appear, the rightmost one
    is the decimal separator.
    """
    cleaned = re.sub(r"[^0-9.,]", "", text or "")
    if not cleaned:
        raise ValueError(f"no numeric price found in {text!r}")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # "49,99" -> 49.99, but "1,299" -> 1299
        head, _, tail = cleaned.rpartition(",")
        cleaned = head.replace(",", "") + "." + tail if len(tail) == 2 else cleaned.replace(",", "")
    return float(cleaned)


def parse_products(html: str, base_url: str = "") -> list[dict]:
    """Extract products from a listing page. Returns a list of dicts
    with keys: name, price, url."""
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for card in soup.select(SELECTORS["card"]):
        name_el = card.select_one(SELECTORS["name"])
        price_el = card.select_one(SELECTORS["price"])
        if not name_el or not price_el:
            continue  # incomplete card (e.g. an ad slot) - skip it
        link_el = card.select_one(SELECTORS["link"])
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
        products.append(
            {
                "name": name_el.get_text(strip=True),
                "price": parse_price(price_el.get_text()),
                "url": url,
            }
        )
    return products


def fetch_html(url: str, timeout: int = 20) -> str:
    """Download a page with a browser-like user agent."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Snapshots & comparison
# ---------------------------------------------------------------------------

def snapshot_name(now: datetime, output_dir: Path) -> Path:
    """Build a unique snapshot filename for this run."""
    base = now.strftime("prices_%Y%m%d_%H%M%S")
    candidate = output_dir / f"{base}.csv"
    counter = 1
    while candidate.exists():
        candidate = output_dir / f"{base}_{counter}.csv"
        counter += 1
    return candidate


def write_snapshot(products: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name", "price", "url"])
        writer.writeheader()
        for product in sorted(products, key=lambda p: p["name"]):
            writer.writerow({**product, "price": f"{product['price']:.2f}"})


def load_snapshot(path: Path) -> dict[str, float]:
    """Read a snapshot CSV back into a {product name: price} mapping."""
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["name"]: float(row["price"]) for row in csv.DictReader(fh)}


def latest_snapshot(output_dir: Path, exclude: Path | None = None) -> Path | None:
    snapshots = sorted(output_dir.glob("prices_*.csv"))
    if exclude is not None:
        snapshots = [s for s in snapshots if s != exclude]
    return snapshots[-1] if snapshots else None


def compare_snapshots(old: dict[str, float], new: dict[str, float]) -> list[dict]:
    """Diff two {name: price} mappings.

    Returns change dicts with keys: type ('drop' | 'rise' | 'new' | 'removed'),
    name, old_price (None for new), new_price (None for removed), pct.
    """
    changes = []
    for name, new_price in new.items():
        if name not in old:
            changes.append({"type": "new", "name": name, "old_price": None,
                            "new_price": new_price, "pct": None})
        elif old[name] != new_price:
            pct = (new_price - old[name]) / old[name] * 100
            changes.append({"type": "drop" if new_price < old[name] else "rise",
                            "name": name, "old_price": old[name],
                            "new_price": new_price, "pct": pct})
    for name, old_price in old.items():
        if name not in new:
            changes.append({"type": "removed", "name": name, "old_price": old_price,
                            "new_price": None, "pct": None})
    return sorted(changes, key=lambda c: c["name"])


def format_change(change: dict) -> str:
    if change["type"] in ("drop", "rise"):
        label = "PRICE DROP" if change["type"] == "drop" else "PRICE RISE"
        return (f"{label}: {change['name']} "
                f"{change['old_price']:.2f} -> {change['new_price']:.2f} "
                f"({change['pct']:+.1f}%)")
    if change["type"] == "new":
        return f"NEW PRODUCT: {change['name']} at {change['new_price']:.2f}"
    return f"REMOVED: {change['name']} (was {change['old_price']:.2f})"


def append_change_log(changes: list[dict], log_path: Path, when: datetime) -> None:
    with log_path.open("a", encoding="utf-8") as fh:
        for change in changes:
            fh.write(f"[{when:%Y-%m-%d %H:%M:%S}] {format_change(change)}\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_once(html: str, output_dir: Path, base_url: str = "") -> dict:
    """Parse one page, snapshot it, and diff against the previous snapshot.

    Returns a summary dict: {count, snapshot (Path), changes (list)}.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    products = parse_products(html, base_url=base_url)
    if not products:
        raise ValueError("no products found - check the page markup / SELECTORS")

    previous_path = latest_snapshot(output_dir)
    snap_path = snapshot_name(datetime.now(), output_dir)
    write_snapshot(products, snap_path)

    changes: list[dict] = []
    if previous_path is not None:
        old = load_snapshot(previous_path)
        new = {p["name"]: p["price"] for p in products}
        changes = compare_snapshots(old, new)
        if changes:
            append_change_log(changes, output_dir / "price_changes.log", datetime.now())
    return {"count": len(products), "snapshot": snap_path, "changes": changes}


def print_summary(summary: dict) -> None:
    print(f"Tracked {summary['count']} products -> {summary['snapshot']}")
    if summary["changes"]:
        print(f"{len(summary['changes'])} change(s) detected:")
        for change in summary["changes"]:
            print(f"  {format_change(change)}")
    else:
        print("No changes vs. the previous snapshot (or first run).")


def run_demo(project_dir: Path) -> None:
    """Offline demo: track the sample shop page twice (v1, then v2 after a
    'price update') and show the detected changes. No network needed."""
    output_dir = project_dir / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)  # start clean so the demo is repeatable

    for label, filename in [("Run 1 - initial prices", "sample_page_v1.html"),
                            ("Run 2 - after the shop updates prices", "sample_page_v2.html")]:
        html = (project_dir / "sample_data" / filename).read_text(encoding="utf-8")
        print(f"\n=== {label} ({filename}) ===")
        print_summary(run_once(html, output_dir))

    print(f"\nSnapshots and price_changes.log are in: {output_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track product prices from a listing page.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="run the offline demo")
    group.add_argument("--url", help="URL of a live listing page to fetch")
    group.add_argument("--source", help="path to a local HTML file to parse")
    parser.add_argument("--output-dir", default="output",
                        help="where snapshots are stored (default: ./output)")
    args = parser.parse_args(argv)

    project_dir = Path(__file__).resolve().parent
    try:
        if args.demo:
            run_demo(project_dir)
        elif args.url:
            print_summary(run_once(fetch_html(args.url), Path(args.output_dir), base_url=args.url))
        else:
            html = Path(args.source).read_text(encoding="utf-8")
            print_summary(run_once(html, Path(args.output_dir)))
    except (ValueError, requests.RequestException, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
