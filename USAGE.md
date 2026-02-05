# Truck Market Scraper - Usage Guide

Multi-source truck listing scraper for the Saline, MI area.

## Features

✅ **Multi-source scraping:**
- Craigslist (7 regional sites: detroit, annarbor, lansing, toledo, saginaw, jackson, flint)
- Facebook Marketplace

✅ **Smart deduplication:**
- Cross-source duplicate detection
- Handles same truck posted in multiple regions
- Hash-based matching + fuzzy matching on vehicle details

✅ **Detailed information extraction:**
- Vehicle condition notes (excellent, good, fair, etc.)
- Maintenance history (new tires, oil changes, timing belt, etc.)
- Known issues (rust, damage, mechanical problems)
- Service records (Carfax, maintenance logs)
- General seller notes

✅ **Database tracking:**
- SQLite database with full history
- Price tracking over time
- Active/inactive status
- First seen / last seen dates

## Quick Start

### 1. Standalone Scraping (Craigslist only)

```bash
cd /opt/openclaw/.openclaw/workspace/truck-market
python3 scraper.py
```

This will scrape all 7 Craigslist regions and store results in `trucks.db`.

### 2. Full Scraping (Craigslist + Facebook)

```bash
python3 integration_test.py
```

Or use with browser from OpenClaw:

```python
from truck_market import scraper

# Assuming 'browser_tool' is provided by OpenClaw
stats = scraper.run_scrape(browser_tool=browser_tool)
```

### 3. Testing Facebook Only

```bash
python3 test_facebook.py
```

## Database Schema

Located at: `/opt/openclaw/.openclaw/workspace/truck-market/trucks.db`

### Main Tables

**listings** - All truck listings
- Vehicle details: year, make, model, trim, mileage
- Pricing: price, original_price, price_per_mile
- Location: location, city, state, distance
- Seller info: vehicle_condition_notes, maintenance_history, known_issues, service_records
- Tracking: first_seen_date, last_seen_date, status, times_seen
- Deduplication: dedup_hash

**price_history** - Price tracking over time

**model_info** - Model reliability and market data (for future use)

**scrape_runs** - Scraping history and statistics

## Search Criteria

- **Location:** Within 100 miles of Saline, MI (48176)
- **Age:** Trucks less than 15 years old (2011-2026)
- **Type:** All truck body styles

## Output Example

```
======================================================================
SCRAPE RESULTS
======================================================================

Total listings found: 483
New listings added: 18
Listings marked inactive: 0

By Source:
  Craigslist: 483 found, 18 new, 0 inactive
  Facebook: 5 found, 5 new, 0 inactive

======================================================================
DATABASE STATISTICS
======================================================================

Total listings: 23
Active listings: 23
  - Craigslist: 18
  - Facebook: 5

Price range: $8,900 - $49,900
Average price: $21,450.00
```

## Files

- `scraper.py` - Main scraper module
- `schema.sql` - Database schema
- `integration_test.py` - Full integration test
- `test_facebook.py` - Facebook-only test
- `run_scraper.py` - Alternative test runner
- `trucks.db` - SQLite database (created on first run)
- `USAGE.md` - This file

## Advanced Usage

### Query the Database

```bash
# Count active listings
python3 -c "import sqlite3; conn = sqlite3.connect('trucks.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM listings WHERE status=\"active\"'); print(cursor.fetchone()[0])"

# Show recent listings
python3 -c "import sqlite3; conn = sqlite3.connect('trucks.db'); cursor = conn.cursor(); cursor.execute('SELECT year, make, model, price FROM listings WHERE status=\"active\" ORDER BY created_at DESC LIMIT 10'); [print(row) for row in cursor.fetchall()]"

# Price statistics by make
python3 -c "import sqlite3; conn = sqlite3.connect('trucks.db'); cursor = conn.cursor(); cursor.execute('SELECT make, COUNT(*), AVG(price), MIN(price), MAX(price) FROM listings WHERE status=\"active\" GROUP BY make'); [print(row) for row in cursor.fetchall()]"
```

### Customize Search Parameters

Edit `scraper.py` to change:

- `CURRENT_YEAR` - Current year for filtering
- `MIN_YEAR` - Minimum year (currently CURRENT_YEAR - 15)
- `CRAIGSLIST_REGIONS` - List of Craigslist regions to scrape
- `FACEBOOK_MARKETPLACE_URL` - Facebook Marketplace search URL

## Troubleshooting

### "No listings found"
- Check internet connection
- Verify search URLs are still valid
- Check Craigslist/Facebook haven't changed their HTML structure

### "Database locked"
- Ensure no other processes are using `trucks.db`
- Close any open SQLite connections

### "Browser tool not provided"
- Facebook scraping requires browser automation
- Pass `browser_tool` parameter to `run_scrape()`

## Future Enhancements

- [ ] More sources (AutoTrader, Cars.com, etc.)
- [ ] Email notifications for new listings
- [ ] Price drop alerts
- [ ] VIN decoding and history lookups
- [ ] Automated valuation using KBB API
- [ ] Web dashboard for browsing listings
