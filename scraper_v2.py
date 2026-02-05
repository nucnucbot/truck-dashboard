#!/usr/bin/env python3
"""
Truck Market Scraper v2 - Rebuilt from scratch
Focus: High data quality through detail page fetching
Target: Consumer pickups only (no commercial trucks)
Region: 7 MI/OH Craigslist regions within 100mi of Saline, MI
"""

import sqlite3
import json
import re
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import urllib.request

# Configuration
DB_PATH = Path(__file__).parent / "trucks.db"
CURRENT_YEAR = 2026
MIN_YEAR = 2011
MAX_YEAR = 2026
SEARCH_POSTAL = "48176"  # Saline, MI
SEARCH_DISTANCE = 100  # miles

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Craigslist regions
REGIONS = [
    'detroit', 'annarbor', 'lansing', 'toledo',
    'saginaw', 'jackson', 'flint'
]

# Model-specific searches (make, model)
PRIORITY_MODELS = [
    ('nissan', 'frontier'),
    ('toyota', 'tacoma'),
    ('ford', 'f-150'),
    ('chevrolet', 'silverado'),
    ('ram', '1500'),
    ('ford', 'ranger'),
    ('toyota', 'tundra'),
    ('chevrolet', 'colorado'),
    ('gmc', 'canyon'),
    ('gmc', 'sierra'),
]

# Commercial truck exclusions (case-insensitive patterns)
COMMERCIAL_EXCLUSIONS = [
    r'\bf-?450\b', r'\bf-?550\b', r'\bf-?650\b', r'\bf-?750\b',
    r'\bbox\s+truck\b', r'\bbucket\s+truck\b', r'\bboom\b',
    r'\bdump\s+truck\b', r'\butility\s+truck\b', r'\bflatbed\b',
    r'\btow\s+truck\b', r'\bmoving\s+truck\b', r'\bservice\s+truck\b',
    r'\bcargo\s+van\b', r'\bdaihatsu\b', r'\be-?450\b'
]

# Allowed consumer pickups (for validation)
CONSUMER_MODELS = {
    'ford': ['f-150', 'f-250', 'f-350', 'ranger', 'maverick'],
    'chevrolet': ['silverado', 'colorado', 's-10', '1500', '2500', '3500'],
    'gmc': ['sierra', 'canyon', '1500', '2500', '3500'],
    'ram': ['1500', '2500', '3500'],
    'dodge': ['ram'],
    'toyota': ['tacoma', 'tundra'],
    'nissan': ['frontier', 'titan'],
    'honda': ['ridgeline'],
    'jeep': ['gladiator'],
}


@dataclass
class Listing:
    """Truck listing data"""
    post_id: str
    url: str
    title: str
    year: Optional[int]
    make: Optional[str]
    model: Optional[str]
    price: Optional[int]
    
    # From detail page
    mileage: Optional[int] = None
    drivetrain: Optional[str] = None
    transmission: Optional[str] = None
    fuel_type: Optional[str] = None
    condition: Optional[str] = None
    title_status: Optional[str] = None
    paint_color: Optional[str] = None
    body_style: Optional[str] = None
    
    location: Optional[str] = None
    region: str = ''
    description: Optional[str] = None
    image_url: Optional[str] = None
    image_count: int = 0
    seller_type: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'id': f'craigslist_{self.post_id}',
            'post_id': self.post_id,
            'url': self.url,
            'title': self.title,
            'year': self.year,
            'make': self.make,
            'model': self.model,
            'price': self.price,
            'mileage': self.mileage,
            'drivetrain': self.drivetrain,
            'transmission': self.transmission,
            'fuel_type': self.fuel_type,
            'condition': self.condition,
            'title_status': self.title_status,
            'paint_color': self.paint_color,
            'body_style': self.body_style,
            'location': self.location,
            'region': self.region,
            'description': self.description,
            'image_url': self.image_url,
            'image_count': self.image_count,
            'seller_type': self.seller_type,
        }


class Database:
    """Database operations"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Load schema from schema.sql if it exists
        schema_path = self.db_path.parent / 'schema.sql'
        if schema_path.exists():
            with open(schema_path) as f:
                conn.executescript(f.read())
            logger.info("Database initialized from schema.sql")
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def insert_listing(self, listing: Listing) -> bool:
        """Insert or update listing. Returns True if new."""
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        
        listing_id = f'craigslist_{listing.post_id}'
        
        # Check if exists
        cursor.execute("SELECT id, price FROM listings WHERE id = ?", (listing_id,))
        existing = cursor.fetchone()
        
        # Calculate derived fields
        price_per_mile = None
        if listing.price and listing.mileage and listing.mileage > 0:
            price_per_mile = listing.price / listing.mileage
        
        if existing:
            # Update
            old_price = existing[1]
            cursor.execute("""
                UPDATE listings SET
                    title = ?, year = ?, make = ?, model = ?, price = ?,
                    mileage = ?, drivetrain = ?, transmission = ?, fuel_type = ?,
                    condition = ?, title_status = ?, paint_color = ?, body_style = ?,
                    location = ?, region = ?, description = ?,
                    image_url = ?, image_count = ?, seller_type = ?,
                    price_per_mile = ?, last_seen_date = ?,
                    times_seen = times_seen + 1, status = 'active',
                    updated_at = ?
                WHERE id = ?
            """, (
                listing.title, listing.year, listing.make, listing.model, listing.price,
                listing.mileage, listing.drivetrain, listing.transmission, listing.fuel_type,
                listing.condition, listing.title_status, listing.paint_color, listing.body_style,
                listing.location, listing.region, listing.description,
                listing.image_url, listing.image_count, listing.seller_type,
                price_per_mile, now, now, listing_id
            ))
            
            # Track price change
            if listing.price and old_price and listing.price != old_price:
                cursor.execute("""
                    INSERT INTO price_history (listing_id, price, observed_date)
                    VALUES (?, ?, ?)
                """, (listing_id, listing.price, now))
            
            conn.commit()
            conn.close()
            return False
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO listings (
                    id, source, post_id, url, title,
                    year, make, model, price, mileage,
                    drivetrain, transmission, fuel_type, condition,
                    title_status, paint_color, body_style,
                    location, region, description,
                    image_url, image_count, seller_type,
                    price_per_mile, first_seen_date, last_seen_date,
                    status, times_seen, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing_id, 'craigslist', listing.post_id, listing.url, listing.title,
                listing.year, listing.make, listing.model, listing.price, listing.mileage,
                listing.drivetrain, listing.transmission, listing.fuel_type, listing.condition,
                listing.title_status, listing.paint_color, listing.body_style,
                listing.location, listing.region, listing.description,
                listing.image_url, listing.image_count, listing.seller_type,
                price_per_mile, now, now, 'active', 1, now
            ))
            
            # Add to price history
            if listing.price:
                cursor.execute("""
                    INSERT INTO price_history (listing_id, price, observed_date)
                    VALUES (?, ?, ?)
                """, (listing_id, listing.price, now))
            
            conn.commit()
            conn.close()
            return True
    
    def record_scrape_run(self, stats: dict):
        """Record scrape run statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO scrape_runs (
                run_date, region, search_type, listings_found,
                new_listings, detail_pages_fetched, duration_seconds, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            stats.get('region', 'all'),
            stats.get('search_type', 'all'),
            stats.get('listings_found', 0),
            stats.get('new_listings', 0),
            stats.get('detail_pages_fetched', 0),
            stats.get('duration_seconds', 0),
            stats.get('status', 'success')
        ))
        
        conn.commit()
        conn.close()
    
    def get_active_listings(self) -> List[dict]:
        """Get all active listings"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, source, url, title, year, make, model, price,
                   mileage, drivetrain, transmission, condition,
                   location, region, description
            FROM listings
            WHERE status = 'active'
            ORDER BY year DESC, mileage ASC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results


class CraigslistScraper:
    """Craigslist scraper with detail page fetching"""
    
    def __init__(self):
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }
        self.detail_fetch_count = 0
    
    def fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML from URL"""
        try:
            req = urllib.request.Request(url, headers=self.session_headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return None
    
    def parse_search_page(self, html: str, region: str) -> List[Tuple[str, str, str, Optional[int], Optional[str]]]:
        """
        Parse search results page.
        Returns list of (post_id, url, title, price, location) tuples.
        """
        results = []
        
        # Match listing items
        pattern = r'<li[^>]*class="[^"]*cl-static-search-result[^"]*"[^>]*>(.*?)</li>'
        items = re.findall(pattern, html, re.DOTALL)
        
        for item in items:
            # Extract URL and post ID
            url_match = re.search(r'href="(https?://[^"]+/(\d+)\.html[^"]*)"', item)
            if not url_match:
                continue
            
            url = url_match.group(1)
            post_id = url_match.group(2)
            
            # Extract title
            title_match = re.search(r'<div[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</div>', item)
            if not title_match:
                title_match = re.search(r'title="([^"]+)"', item)
            
            title = None
            if title_match:
                title = title_match.group(1).strip()
            
            # Extract price
            price = None
            price_match = re.search(r'<div[^>]*class="[^"]*price[^"]*"[^>]*>\$([0-9,]+)</div>', item)
            if price_match:
                price_str = price_match.group(1).replace(',', '')
                try:
                    price = int(price_str)
                except ValueError:
                    pass
            
            # Extract location
            location = None
            loc_match = re.search(r'<div[^>]*class="[^"]*location[^"]*"[^>]*>([^<]+)</div>', item)
            if loc_match:
                location = loc_match.group(1).strip()
            
            if title:
                results.append((post_id, url, title, price, location))
        
        return results
    
    def is_commercial_truck(self, title: str) -> bool:
        """Check if listing is a commercial truck (should be excluded)"""
        title_lower = title.lower()
        
        for pattern in COMMERCIAL_EXCLUSIONS:
            if re.search(pattern, title_lower):
                return True
        
        return False
    
    def extract_basic_info(self, title: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Extract year, make, model from title"""
        title_lower = title.lower()
        
        # Extract year
        year_match = re.search(r'\b(20\d{2}|201[1-9])\b', title)
        year = int(year_match.group(1)) if year_match else None
        
        # Extract make
        make = None
        for m, models in CONSUMER_MODELS.items():
            if m in title_lower or (m == 'chevrolet' and 'chevy' in title_lower):
                make = m.title()
                if make == 'Chevrolet' and 'chevy' in title_lower and 'chevrolet' not in title_lower:
                    make = 'Chevrolet'
                break
        
        # Extract model
        model = None
        if make:
            make_key = make.lower()
            if make_key == 'chevrolet':
                make_key = 'chevrolet' if 'chevrolet' in title_lower else 'chevrolet'
            
            for m in CONSUMER_MODELS.get(make_key, []):
                # Match model with word boundaries
                if re.search(r'\b' + re.escape(m) + r'\b', title_lower):
                    model = m.upper() if m.isdigit() else m.title()
                    break
        
        return year, make, model
    
    def fetch_detail_page(self, url: str) -> Optional[dict]:
        """
        Fetch and parse detail page for comprehensive data.
        Returns dict with extracted attributes.
        """
        self.detail_fetch_count += 1
        
        html = self.fetch_html(url)
        if not html:
            return None
        
        data = {}
        
        # Extract attributes from CL's div.attr structure:
        # <div class="attr auto_miles">
        #   <span class="labl">odometer:</span>
        #   <span class="valu">104,000</span>
        # </div>
        attr_pattern = r'<div[^>]*class="attr[^"]*"[^>]*>\s*<span[^>]*class="labl"[^>]*>([^<]+)</span>\s*<span[^>]*class="valu"[^>]*>(.*?)</span>'
        attrs = re.findall(attr_pattern, html, re.DOTALL)
        
        for label, value_html in attrs:
            label_clean = label.strip().lower().rstrip(':')
            # Strip HTML tags from value (some have <a> links)
            value_clean = re.sub(r'<[^>]+>', '', value_html).strip()
            
            if 'odometer' in label_clean:
                mileage_match = re.search(r'[\d,]+', value_clean)
                if mileage_match:
                    data['mileage'] = int(mileage_match.group(0).replace(',', ''))
            
            elif label_clean == 'drive':
                data['drivetrain'] = value_clean
            
            elif 'transmission' in label_clean:
                data['transmission'] = value_clean
            
            elif 'fuel' in label_clean:
                data['fuel_type'] = value_clean
            
            elif 'condition' in label_clean:
                data['condition'] = value_clean
            
            elif 'title status' in label_clean:
                data['title_status'] = value_clean
            
            elif 'paint color' in label_clean or 'color' in label_clean:
                data['paint_color'] = value_clean
            
            elif 'type' in label_clean and 'body_style' not in data:
                data['body_style'] = value_clean
        
        # Extract description from postingbody
        desc_match = re.search(
            r'<section[^>]*id="postingbody"[^>]*>(.*?)</section>',
            html, re.DOTALL
        )
        if desc_match:
            desc_html = desc_match.group(1)
            # Remove QR code text and script tags
            desc_html = re.sub(r'QR Code Link to This Post', '', desc_html)
            desc_html = re.sub(r'<script[^>]*>.*?</script>', '', desc_html, flags=re.DOTALL)
            # Strip HTML tags
            desc_text = re.sub(r'<[^>]+>', '', desc_html)
            # Clean whitespace
            desc_text = ' '.join(desc_text.split()).strip()
            if desc_text:
                data['description'] = desc_text
        
        # Extract image info
        image_match = re.search(r'<img[^>]*src="([^"]+)"[^>]*>', html)
        if image_match:
            data['image_url'] = image_match.group(1)
        
        # Count images
        image_count = len(re.findall(r'<img[^>]*class="[^"]*thumb[^"]*"', html))
        data['image_count'] = image_count
        
        # Detect seller type (dealer vs owner)
        if re.search(r'\bdealer\b', html, re.IGNORECASE):
            data['seller_type'] = 'dealer'
        else:
            data['seller_type'] = 'owner'
        
        # Extract price from detail page
        # Try the price element first
        price_match = re.search(r'<span[^>]*class="[^"]*price[^"]*"[^>]*>\$([0-9,]+)</span>', html)
        if not price_match:
            # Try anywhere in the HTML
            price_match = re.search(r'\$\s*(\d[\d,]{2,})', html)
        
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            try:
                data['price'] = int(price_str)
            except ValueError:
                pass
        
        return data
    
    def scrape_search(self, region: str, search_term: str = 'truck', seen_ids: Set[str] = None) -> List[Listing]:
        """
        Scrape a single search and fetch detail pages for new listings.
        search_term: 'truck' for general, or 'make+model' for specific
        seen_ids: set of already-processed post IDs to skip
        """
        if seen_ids is None:
            seen_ids = set()
        
        # Build search URL
        url = (
            f"https://{region}.craigslist.org/search/cta"
            f"?auto_make_model={search_term}"
            f"&min_auto_year={MIN_YEAR}"
            f"&max_auto_year={MAX_YEAR}"
            f"&search_distance={SEARCH_DISTANCE}"
            f"&postal={SEARCH_POSTAL}"
        )
        
        search_label = search_term.replace('+', ' ').title()
        logger.info(f"  Searching {region} for {search_label}...")
        
        html = self.fetch_html(url)
        if not html:
            logger.warning(f"  Failed to fetch {region} {search_label}")
            return []
        
        # Parse search results
        results = self.parse_search_page(html, region)
        
        # Filter before fetching detail pages
        new_results = []
        for post_id, listing_url, title, search_price, location in results:
            # Skip already-seen listings (dedup BEFORE detail fetch)
            if post_id in seen_ids:
                continue
            
            # Filter commercial trucks BEFORE detail fetch
            if self.is_commercial_truck(title):
                continue
            
            # Extract basic info
            year, make, model = self.extract_basic_info(title)
            
            # Validate year
            if not year or year < MIN_YEAR or year > MAX_YEAR:
                continue
            
            # Validate search-page price if available
            if search_price is not None and (search_price < 1000 or search_price > 80000):
                continue
            
            new_results.append((post_id, listing_url, title, search_price, location, year, make, model))
        
        logger.info(f"  Found {len(results)} total, {len(new_results)} new after filtering")
        
        # Limit detail page fetches per region-search to keep runtime reasonable
        MAX_DETAILS_PER_SEARCH = 50
        if len(new_results) > MAX_DETAILS_PER_SEARCH:
            logger.info(f"  Limiting to {MAX_DETAILS_PER_SEARCH} detail page fetches (of {len(new_results)})")
            new_results = new_results[:MAX_DETAILS_PER_SEARCH]
        
        listings = []
        
        for post_id, listing_url, title, search_price, location, year, make, model in new_results:
            # Create listing with search-page price
            listing = Listing(
                post_id=post_id,
                url=listing_url,
                title=title,
                year=year,
                make=make,
                model=model,
                price=search_price,  # Keep search-page price
                location=location,
                region=region
            )
            
            # Fetch detail page (THE CRITICAL STEP)
            logger.info(f"    Fetching detail: {title[:60]}...")
            detail_data = self.fetch_detail_page(listing_url)
            
            if detail_data:
                # Update listing with detail data
                listing.mileage = detail_data.get('mileage')
                listing.drivetrain = detail_data.get('drivetrain')
                listing.transmission = detail_data.get('transmission')
                listing.fuel_type = detail_data.get('fuel_type')
                listing.condition = detail_data.get('condition')
                listing.title_status = detail_data.get('title_status')
                listing.paint_color = detail_data.get('paint_color')
                listing.body_style = detail_data.get('body_style')
                listing.description = detail_data.get('description')
                listing.image_url = detail_data.get('image_url')
                listing.image_count = detail_data.get('image_count', 0)
                listing.seller_type = detail_data.get('seller_type')
                
                # Use detail page price if search page didn't have one
                if not listing.price and detail_data.get('price'):
                    listing.price = detail_data['price']
            
            # Final price validation
            if not listing.price or listing.price < 1000 or listing.price > 80000:
                logger.debug(f"  Skipping invalid price: {title} (${listing.price})")
                continue
            
            listings.append(listing)
            seen_ids.add(post_id)  # Mark as seen
            
            # Rate limit: 1.5 seconds between detail fetches
            time.sleep(1.5)
        
        return listings
    
    def scrape_all(self, db: 'Database' = None) -> List[Listing]:
        """
        Execute full two-phase scrape across all regions.
        Phase 1: General truck search
        Phase 2: Model-specific searches
        Writes to DB incrementally if provided.
        """
        all_listings = []
        seen_ids: Set[str] = set()
        new_count = 0
        
        # Phase 1: General truck search
        logger.info("=== PHASE 1: General Truck Search ===")
        for region in REGIONS:
            listings = self.scrape_search(region, 'truck', seen_ids)
            all_listings.extend(listings)
            
            # Write incrementally to DB
            if db:
                for listing in listings:
                    if db.insert_listing(listing):
                        new_count += 1
        
        logger.info(f"Phase 1 complete: {len(all_listings)} unique listings")
        logger.info(f"Detail pages fetched so far: {self.detail_fetch_count}")
        
        # Phase 2: Model-specific searches
        logger.info("\n=== PHASE 2: Model-Specific Searches ===")
        phase2_start = len(all_listings)
        
        for make, model in PRIORITY_MODELS:
            search_term = f"{make}+{model}"
            logger.info(f"\nSearching for {make.title()} {model.title()}:")
            
            for region in REGIONS:
                listings = self.scrape_search(region, search_term, seen_ids)
                all_listings.extend(listings)
                
                # Write incrementally to DB
                if db:
                    for listing in listings:
                        if db.insert_listing(listing):
                            new_count += 1
        
        phase2_count = len(all_listings) - phase2_start
        logger.info(f"\nPhase 2 complete: {phase2_count} additional unique listings")
        logger.info(f"Total listings: {len(all_listings)}")
        logger.info(f"Total detail pages fetched: {self.detail_fetch_count}")
        logger.info(f"New listings saved to DB: {new_count}")
        
        return all_listings


def generate_summary(db: Database) -> dict:
    """Generate comprehensive summary statistics"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    summary = {}
    
    # Total counts
    cursor.execute("SELECT COUNT(*) FROM listings WHERE status = 'active'")
    summary['total_active'] = cursor.fetchone()[0]
    
    # By make
    cursor.execute("""
        SELECT make, COUNT(*) as count
        FROM listings
        WHERE status = 'active' AND make IS NOT NULL
        GROUP BY make
        ORDER BY count DESC
    """)
    summary['by_make'] = dict(cursor.fetchall())
    
    # By region
    cursor.execute("""
        SELECT region, COUNT(*) as count
        FROM listings
        WHERE status = 'active' AND region IS NOT NULL
        GROUP BY region
        ORDER BY count DESC
    """)
    summary['by_region'] = dict(cursor.fetchall())
    
    # Data completeness
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN mileage IS NOT NULL THEN 1 ELSE 0 END) as has_mileage,
            SUM(CASE WHEN drivetrain IS NOT NULL THEN 1 ELSE 0 END) as has_drivetrain,
            SUM(CASE WHEN transmission IS NOT NULL THEN 1 ELSE 0 END) as has_transmission,
            SUM(CASE WHEN condition IS NOT NULL THEN 1 ELSE 0 END) as has_condition,
            SUM(CASE WHEN description IS NOT NULL THEN 1 ELSE 0 END) as has_description
        FROM listings
        WHERE status = 'active'
    """)
    row = cursor.fetchone()
    if row and row[0] > 0:
        total = row[0]
        summary['completeness'] = {
            'mileage': f"{(row[1]/total)*100:.1f}%",
            'drivetrain': f"{(row[2]/total)*100:.1f}%",
            'transmission': f"{(row[3]/total)*100:.1f}%",
            'condition': f"{(row[4]/total)*100:.1f}%",
            'description': f"{(row[5]/total)*100:.1f}%",
        }
    
    # Nissan Frontier specific
    cursor.execute("""
        SELECT COUNT(*) FROM listings
        WHERE status = 'active' AND make = 'Nissan' AND model LIKE '%Frontier%'
    """)
    summary['nissan_frontier_count'] = cursor.fetchone()[0]
    
    conn.close()
    return summary


def export_listings(db: Database, output_path: Path):
    """Export active listings to JSON"""
    listings = db.get_active_listings()
    
    with open(output_path, 'w') as f:
        json.dump(listings, f, indent=2)
    
    logger.info(f"Exported {len(listings)} listings to {output_path}")


def main():
    """Main execution"""
    start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("TRUCK MARKET SCRAPER V2")
    logger.info("=" * 70)
    
    # Initialize database
    db = Database(DB_PATH)
    
    # Run scraper (writes to DB incrementally)
    scraper = CraigslistScraper()
    listings = scraper.scrape_all(db=db)
    
    # Count results
    new_count = len(listings)  # approximate since incremental
    
    logger.info(f"New listings: {new_count}")
    logger.info(f"Listings processed: {len(listings)}")
    
    # Record scrape run
    duration = time.time() - start_time
    db.record_scrape_run({
        'listings_found': len(listings),
        'new_listings': new_count,
        'detail_pages_fetched': scraper.detail_fetch_count,
        'duration_seconds': duration,
        'status': 'success'
    })
    
    # Generate summary
    logger.info("\n=== SCRAPE SUMMARY ===")
    summary = generate_summary(db)
    
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"\nTotal active listings: {summary['total_active']}")
    print(f"Detail pages fetched: {scraper.detail_fetch_count}")
    print(f"Duration: {duration/60:.1f} minutes")
    
    print("\n--- By Make ---")
    for make, count in summary['by_make'].items():
        print(f"  {make}: {count}")
    
    print("\n--- By Region ---")
    for region, count in summary['by_region'].items():
        print(f"  {region}: {count}")
    
    print("\n--- Data Completeness ---")
    for field, pct in summary['completeness'].items():
        print(f"  {field}: {pct}")
    
    print(f"\n--- Nissan Frontier (PRIORITY) ---")
    print(f"  Count: {summary['nissan_frontier_count']}")
    
    # Export to JSON
    export_path = DB_PATH.parent / 'listings_export.json'
    export_listings(db, export_path)
    
    # Show sample Nissan Frontiers
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT year, title, price, mileage, drivetrain, condition, url
        FROM listings
        WHERE status = 'active' AND make = 'Nissan' AND model LIKE '%Frontier%'
        ORDER BY year DESC, mileage ASC
        LIMIT 5
    """)
    
    frontiers = cursor.fetchall()
    if frontiers:
        print("\n--- Sample Nissan Frontier Listings ---")
        for year, title, price, mileage, drivetrain, condition, url in frontiers:
            price_str = f"${price:,}" if price else "N/A"
            miles_str = f"{mileage:,}mi" if mileage else "N/A"
            dt_str = drivetrain or "N/A"
            cond_str = condition or "N/A"
            print(f"\n  {year} - {title[:50]}")
            print(f"    {price_str} | {miles_str} | {dt_str} | {cond_str}")
            print(f"    {url}")
    
    conn.close()
    
    print(f"\n{'='*70}")
    logger.info("Scrape complete!")


if __name__ == '__main__':
    main()
