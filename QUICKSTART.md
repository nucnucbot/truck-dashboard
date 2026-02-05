# Truck Market Intelligence - Quick Start

## What's Running

**Daily scrape**: Every day at 10 AM EST
- Collects ALL trucks <15 years old, 100 mile radius from Saline
- Tracks prices, mileage, make/model, location
- Marks listings as active/inactive
- Detects price drops

## Check The Data

```bash
# View stats
cd /opt/openclaw/.openclaw/workspace/truck-market
python3 db_helpers.py

# Query directly
sqlite3 trucks.db "SELECT COUNT(*) FROM listings WHERE status='active'"

# Best deals (price per mile under $100)
sqlite3 trucks.db "
SELECT year, make, model, price, mileage, 
       ROUND(price_per_mile,2) as ppm, location
FROM listings 
WHERE status='active' AND price_per_mile < 100
ORDER BY price_per_mile ASC 
LIMIT 20;
"

# Recent price drops
sqlite3 trucks.db "
SELECT l.year, l.make, l.model, l.price, ph.price as was,
       (ph.price - l.price) as saved
FROM listings l
JOIN price_history ph ON l.id = ph.listing_id
WHERE l.status='active' AND ph.price > l.price
ORDER BY saved DESC LIMIT 10;
"
```

## Current Status

- ✅ Database schema created (`trucks.db`)
- ✅ Scraper framework built (`scraper.py`, `db_helpers.py`)
- ✅ Daily cron job scheduled (10 AM EST)
- ✅ Deduplication logic implemented
- ⏳ First scrape runs tomorrow at 10 AM
- ⏳ After 1-2 days of data: build analytics frontend

## What's Tracked

Every listing stores:
- Year, make, model, trim
- Price (current + history of changes)
- Mileage
- Location, distance from Saline
- First seen / last seen dates
- Active vs inactive status
- Facebook URL
- Images

## Next Steps (Once Data Accumulates)

1. **Analytics** (after 2-3 days)
   - Market trends by make/model
   - Best value analysis
   - Price drop alerts

2. **Frontend** (when you're ready)
   - Create GitHub repo
   - Build dashboard (React/Next.js)
   - Deploy to Vercel
   - Charts, filters, trends

3. **Intelligence Layer**
   - Research common issues per model/year
   - KBB pricing integration
   - Risk/reward scoring algorithm

## Files

```
truck-market/
├── trucks.db           # SQLite database (0 listings currently)
├── schema.sql          # Database structure
├── scraper.py          # Core scraping + data logic
├── db_helpers.py       # Query helpers
├── README.md           # Full documentation
└── QUICKSTART.md       # This file
```

## Cron Jobs

- **9 AM**: Nissan Frontier specific search (your original request)
- **10 AM**: Full truck market scrape (this new system)
