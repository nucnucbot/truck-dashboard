-- Truck Market Intelligence Database Schema v2
-- Consumer pickups within 100 miles of Saline, MI (48176)

CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,           -- craigslist_{post_id}
    source TEXT NOT NULL DEFAULT 'craigslist',
    post_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    
    -- Vehicle details
    year INTEGER NOT NULL,
    make TEXT,
    model TEXT,
    trim TEXT,
    body_style TEXT,
    
    -- Pricing
    price INTEGER NOT NULL,
    
    -- From detail page
    mileage INTEGER,
    drivetrain TEXT,               -- 4wd, rwd, fwd
    transmission TEXT,             -- automatic, manual
    fuel_type TEXT,                -- gas, diesel, hybrid, electric
    condition TEXT,                -- excellent, good, fair, etc
    title_status TEXT,             -- clean, rebuilt, salvage
    paint_color TEXT,
    
    -- Location
    location TEXT,
    region TEXT,                   -- craigslist region
    
    -- Content
    description TEXT,
    image_url TEXT,
    image_count INTEGER DEFAULT 0,
    seller_type TEXT,              -- owner, dealer
    
    -- Tracking
    first_seen_date TEXT NOT NULL,
    last_seen_date TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    times_seen INTEGER DEFAULT 1,
    
    -- Computed
    price_per_mile REAL,
    
    -- Timestamps
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_year ON listings(year);
CREATE INDEX IF NOT EXISTS idx_make_model ON listings(make, model);
CREATE INDEX IF NOT EXISTS idx_price ON listings(price);
CREATE INDEX IF NOT EXISTS idx_mileage ON listings(mileage);
CREATE INDEX IF NOT EXISTS idx_post_id ON listings(post_id);

-- Price history
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    price INTEGER NOT NULL,
    observed_date TEXT NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);

-- Scrape run history
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    region TEXT,
    search_type TEXT,
    listings_found INTEGER,
    new_listings INTEGER,
    detail_pages_fetched INTEGER,
    duration_seconds REAL,
    status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
