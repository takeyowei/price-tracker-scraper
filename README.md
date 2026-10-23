# Price Tracker Scraper

A small, dependable price-monitoring tool: it reads the product listing page
of an online shop, saves a CSV snapshot of every product's price, and reports
exactly what changed since the last run — price drops, price rises, new
products, and removed products.

Built with `requests` + `BeautifulSoup`. Runs fully offline in demo mode.

## Features

- Parses product name, price, and URL from listing-page HTML (CSS selectors
  are centralised in one `SELECTORS` dict, easy to adapt to any shop layout)
- Handles common price formats: `$1,299.99`, `1.299,99 €`, `49,99`, …
- Timestamped CSV snapshots, one per run
- Automatic diff against the previous snapshot, appended to
  `price_changes.log` with percentage change
- Offline demo mode with bundled sample shop pages — no network needed
- Unit + end-to-end tests included

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Offline demo (recommended first run)

```bash
python price_tracker.py --demo
```

This tracks the bundled sample shop twice — first with its original prices,
then after a simulated price update — and prints the detected changes.

### Track a local HTML file

```bash
python price_tracker.py --source sample_data/sample_page_v1.html --output-dir output
```

### Track a live page

```bash
python price_tracker.py --url "https://example-shop.com/laptops" --output-dir output
```

Run it on a schedule (cron, Task Scheduler, …) and every run is compared
against the previous one.

## Sample output

```
=== Run 2 - after the shop updates prices (sample_page_v2.html) ===
Tracked 4 products -> output/prices_20260101_090015.csv
4 change(s) detected:
  PRICE DROP: Aurora Wireless Headphones 129.99 -> 99.99 (-23.1%)
  NEW PRODUCT: ClearView 27-inch Monitor Arm at 74.99
  REMOVED: ErgoFlex Laptop Stand (was 59.99)
  PRICE RISE: MechType Mechanical Keyboard K87 89.50 -> 94.00 (+5.0%)
```

Snapshot CSV:

```csv
name,price,url
Aurora Wireless Headphones,99.99,/products/aurora-wireless-headphones
ClearView 27-inch Monitor Arm,74.99,/products/clearview-monitor-arm
```

## Tests

```bash
python -m pytest tests/ -v
```

## Adapting it to a real shop

1. Open the shop's listing page and inspect the product card markup.
2. Update `SELECTORS` in `price_tracker.py` (card / name / price / link).
3. Check the site's Terms of Service and `robots.txt` before scraping, keep
   the request rate polite, and cache pages where possible.

## License

MIT — free to use as a starting point for your own monitoring setup.
