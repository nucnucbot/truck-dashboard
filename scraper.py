#!/usr/bin/env python3
"""
Truck Market Intelligence Scraper
Multi-source truck listing aggregator for Saline, MI area
Supports: Craigslist, Facebook Marketplace, and other sources

Features:
- Scrapes trucks <15 years old within 100 miles of Saline, MI (48176)
- Multi-source aggregation with deduplication
- Price tracking and analytics
- Database persistence
- Detailed seller information extraction
"""

import sqlite3
import json
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from urllib.parse import urljoin, parse_qs, urlparse
import urllib.request
import html.parser
import hashlib

DB_PATH = Path(__file__).parent / "trucks.db"
CURRENT_YEAR = 2026
MIN_YEAR = CURRENT_YEAR - 15  # Trucks under 15 years old

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Truck makes and models for parsing
TRUCK_MAKES = {
    'ford', 'chevrolet', 'chevy', 'gmc', 'ram', 'dodge', 'toyota', 
    'nissan', 'honda', 'jeep', 'mazda', 'isuzu', 'volkswagen', 'vw',
    'kia', 'hyundai', 'mitsubishi'
}

TRUCK_MODELS = {
    'f-150', 'f150', 'f-250', 'f250', 'f-350', 'f350', 'f-450', 'f450', 'f-550', 'f550',
    'silverado', 'colorado', 'canyon', 'sierra',
    'ram 1500', 'ram 2500', 'ram 3500', '1500', '2500', '3500',
    'tacoma', 'tundra', 'frontier', 'titan',
    'ridgeline', 'ranger', 'gladiator', 'wrangler', 'colorado',
    'maverick', 'lightning', 'electric'
}

# Craigslist regions to search (within 100 miles of Saline, MI)
CRAIGSLIST_REGIONS = [
    'detroit',      # Detroit metro
    'annarbor',     # Ann Arbor
    'lansing',      # Lansing
    'toledo',       # Toledo, OH
    'saginaw',      # Saginaw/Midland
    'jackson',      # Jackson
    'flint',        # Flint
]

# Specific truck models to search for (in addition to generic truck search)
# Format: (make, model) for URL construction
SPECIFIC_TRUCK_MODELS = [
    ('nissan', 'frontier'),       # PRIORITY - Eric is shopping for this
    ('toyota', 'tacoma'),
    ('ford', 'f-150'),
    ('chevrolet', 'silverado'),
    ('ram', '1500'),
    ('ford', 'ranger'),
    ('toyota', 'tundra'),
    ('chevrolet', 'colorado'),
    ('gmc', 'canyon'),
]

# Facebook Marketplace category ID for Michigan (108622215829424)
FACEBOOK_MARKETPLACE_URL = (
    "https://www.facebook.com/marketplace/108622215829424/trucks"
    "?minYear=2011&maxYear=2026&radius=160&exact=false"
)

# Facebook Marketplace URL
FACEBOOK_MARKETPLACE_URL = "https://www.facebook.com/marketplace/108622215829424/trucks?minYear=2011&maxYear=2026&radius=160&exact=false"


@dataclass
class TruckListing:
    """Standardized truck listing format"""
    source: str  # 'craigslist', 'facebook', etc.
    source_id: str  # Unique ID from source
    title: str
    price: Optional[int] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    mileage: Optional[int] = None
    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    url: str = ""
    description: Optional[str] = None
    primary_image_url: Optional[str] = None
    image_urls: List[str] = field(default_factory=list)
    seller_type: Optional[str] = None  # 'private', 'dealer'
    body_style: Optional[str] = None
    drivetrain: Optional[str] = None
    condition: Optional[str] = None
    
    # Detailed seller information
    vehicle_condition_notes: Optional[str] = None
    maintenance_history: Optional[str] = None
    known_issues: Optional[str] = None
    service_records: Optional[str] = None
    seller_notes: Optional[str] = None
    
    def __post_init__(self):
        # Generate database ID from source and source_id
        self.db_id = f"{self.source}_{self.source_id}"
    
    def get_dedup_key(self) -> str:
        """Generate a deduplication key for cross-source matching"""
        # Normalize for comparison
        title_norm = self.title.lower().strip() if self.title else ""
        price_str = str(self.price) if self.price else "0"
        location_norm = self.location.lower().strip() if self.location else ""
        
        # Create hash of normalized data
        key_data = f"{title_norm}|{price_str}|{location_norm}"
        return hashlib.md5(key_data.encode()).hexdigest()


def init_db():
    """Initialize the database with schema"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # First, load and execute the schema.sql file
    schema_path = Path(__file__).parent / "schema.sql"
    try:
        with open(schema_path) as f:
            conn.executescript(f.read())
        logger.info("Database schema initialized from schema.sql")
    except Exception as e:
        logger.warning(f"Could not load schema.sql: {e}")
        conn.commit()
        conn.close()
        return None
    
    # Check if we need to add new columns (in case of upgrades)
    try:
        cursor.execute("PRAGMA table_info(listings)")
        columns = {row[1] for row in cursor.fetchall()}
        
        new_columns = {
            'vehicle_condition_notes': 'TEXT',
            'maintenance_history': 'TEXT',
            'known_issues': 'TEXT',
            'service_records': 'TEXT',
            'seller_notes': 'TEXT',
            'dedup_hash': 'TEXT'
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                logger.info(f"Adding column {col_name} to listings table")
                try:
                    cursor.execute(f"ALTER TABLE listings ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    # Column might already exist
                    pass
        
        # Create index on dedup_hash if it doesn't exist
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_listings_dedup_hash 
            ON listings(dedup_hash)
        """)
        
        conn.commit()
    except Exception as e:
        logger.debug(f"Schema upgrade note: {e}")
    
    # Close connection - callers should use get_connection() for their own connections
    conn.close()
    return None


def get_connection():
    """Get a database connection"""
    return sqlite3.connect(DB_PATH)


# ============================================================================
# CRAIGSLIST SCRAPER
# ============================================================================

def fetch_craigslist_html(region: str, search_url: str) -> Optional[str]:
    """
    Fetch HTML from Craigslist search page
    """
    try:
        req = urllib.request.Request(
            search_url,
            headers={'User-Agent': 'Mozilla/5.0 (Linux; OpenClaw Browser)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
            return html
    except Exception as e:
        logger.error(f"Error fetching Craigslist {region}: {e}")
        return None


def parse_craigslist_price(price_str: str) -> Optional[int]:
    """Parse price from Craigslist format"""
    if not price_str:
        return None
    # Remove currency symbol and commas
    clean = re.sub(r'[$,]', '', price_str.strip())
    try:
        return int(float(clean))
    except ValueError:
        return None


def extract_detailed_info(description: str) -> Dict[str, Optional[str]]:
    """
    Extract detailed seller information from description text
    Returns dict with: vehicle_condition_notes, maintenance_history, 
    known_issues, service_records, seller_notes
    """
    if not description:
        return {
            'vehicle_condition_notes': None,
            'maintenance_history': None,
            'known_issues': None,
            'service_records': None,
            'seller_notes': None
        }
    
    desc_lower = description.lower()
    
    # Extract condition mentions
    condition_patterns = [
        r'(excellent|great|good|fair|poor)\s+condition',
        r'condition[:\s]+(excellent|great|good|fair|poor)',
        r'(well\s+maintained|meticulously\s+maintained|garage\s+kept)',
        r'(mint|pristine|immaculate|showroom)\s+condition'
    ]
    condition_notes = []
    for pattern in condition_patterns:
        matches = re.findall(pattern, desc_lower)
        condition_notes.extend(matches)
    
    # Extract maintenance history
    maintenance_patterns = [
        r'(new|replaced|recent)\s+(tire|tires|brakes|battery|alternator|starter)',
        r'(oil\s+change|transmission\s+service|tune[\s-]up)',
        r'(timing\s+belt|serpentine\s+belt|chain)',
        r'(spark\s+plugs|air\s+filter|fuel\s+filter)',
        r'(\d+k|\d+,\d+)\s+miles?\s+(service|maintenance)',
        r'(regular|scheduled)\s+(maintenance|service)',
        r'(dealer|shop)\s+(serviced|maintained)'
    ]
    maintenance_notes = []
    for pattern in maintenance_patterns:
        matches = re.findall(pattern, desc_lower, re.IGNORECASE)
        for match in matches:
            # Get context around match
            match_str = match if isinstance(match, str) else ' '.join(match)
            idx = desc_lower.find(match_str.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(description), idx + len(match_str) + 50)
                context = description[start:end].strip()
                if context not in maintenance_notes:
                    maintenance_notes.append(context)
    
    # Extract known issues
    issue_patterns = [
        r'(needs|need|require|requires)\s+(repair|work|attention|fixing)',
        r'(rust|dent|scratch|damage|crack|leak)',
        r'(not\s+working|doesn\'t\s+work|inop|broken)',
        r'(check\s+engine|warning\s+light)',
        r'(minor|small|some)\s+(issue|problem|damage)',
        r'(as[\s-]is|sold\s+as[\s-]is)'
    ]
    issue_notes = []
    for pattern in issue_patterns:
        matches = re.findall(pattern, desc_lower, re.IGNORECASE)
        for match in matches:
            match_str = match if isinstance(match, str) else ' '.join(match)
            idx = desc_lower.find(match_str.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(description), idx + len(match_str) + 50)
                context = description[start:end].strip()
                if context not in issue_notes:
                    issue_notes.append(context)
    
    # Extract service records
    service_patterns = [
        r'(service\s+records?|maintenance\s+records?|history)',
        r'(carfax|autocheck|vehicle\s+history)',
        r'(one\s+owner|two\s+owner|original\s+owner)',
        r'(clean\s+title|clear\s+title|salvage|rebuilt)'
    ]
    service_notes = []
    for pattern in service_patterns:
        matches = re.findall(pattern, desc_lower, re.IGNORECASE)
        for match in matches:
            match_str = match if isinstance(match, str) else ' '.join(match)
            idx = desc_lower.find(match_str.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(description), idx + len(match_str) + 50)
                context = description[start:end].strip()
                if context not in service_notes:
                    service_notes.append(context)
    
    return {
        'vehicle_condition_notes': '; '.join(condition_notes[:3]) if condition_notes else None,
        'maintenance_history': ' | '.join(maintenance_notes[:5]) if maintenance_notes else None,
        'known_issues': ' | '.join(issue_notes[:5]) if issue_notes else None,
        'service_records': '; '.join(service_notes[:3]) if service_notes else None,
        'seller_notes': description[:500] if description else None  # Store first 500 chars as general notes
    }


def fetch_craigslist_detail_page(url: str) -> Optional[str]:
    """Fetch full Craigslist detail page for description"""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Linux; OpenClaw Browser)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        logger.debug(f"Error fetching detail page {url}: {e}")
        return None


def extract_craigslist_description(html: str) -> Optional[str]:
    """Extract description from Craigslist detail page"""
    if not html:
        return None
    
    # Try to find the posting body
    match = re.search(r'<section id="postingbody">(.*?)</section>', html, re.DOTALL)
    if match:
        body = match.group(1)
        # Remove QR code text
        body = re.sub(r'QR Code Link to This Post', '', body)
        # Strip HTML tags
        body = re.sub(r'<[^>]+>', '', body)
        # Clean up whitespace
        body = ' '.join(body.split())
        return body.strip()
    
    return None


def parse_craigslist_listing(item_html: str, region: str) -> Optional[TruckListing]:
    """
    Parse a single Craigslist listing from HTML
    """
    try:
        # Extract title
        title_match = re.search(r'title="([^"]+)"', item_html)
        if not title_match:
            title_match = re.search(r'<div class="title">([^<]+)</div>', item_html)
        
        title = title_match.group(1).strip() if title_match else None
        if not title:
            return None
        
        # Extract URL
        url_match = re.search(r'href="(https?://[^"]+)"', item_html)
        if not url_match:
            return None
        url = url_match.group(1)
        
        # Extract listing ID from URL
        id_match = re.search(r'/(\d+)\.html', url)
        listing_id = id_match.group(1) if id_match else None
        if not listing_id:
            return None
        
        # Extract price
        price_match = re.search(r'<div class="price">([^<]+)</div>', item_html)
        price = parse_craigslist_price(price_match.group(1)) if price_match else None
        
        # Extract location
        location_match = re.search(r'<div class="location">\s*([^<]+?)\s*</div>', item_html)
        location = location_match.group(1).strip() if location_match else None
        
        # Parse year, make, model from title
        year = extract_year(title)
        make, model = extract_make_model(title)
        mileage = parse_mileage(title)
        
        # Fetch detail page for description (optional - can be slow)
        description = None
        # description = extract_craigslist_description(fetch_craigslist_detail_page(url))
        
        # Extract detailed info from description
        detailed_info = extract_detailed_info(description)
        
        # Create listing object
        listing = TruckListing(
            source='craigslist',
            source_id=listing_id,
            title=title,
            price=price,
            year=year,
            make=make,
            model=model,
            mileage=mileage,
            location=location,
            url=url,
            description=description,
            **detailed_info
        )
        
        return listing
    except Exception as e:
        logger.debug(f"Error parsing Craigslist listing: {e}")
        return None


def scrape_craigslist_region(region: str, make_model: str = "truck") -> List[TruckListing]:
    """
    Scrape a single Craigslist region
    
    Args:
        region: Craigslist region name (e.g., 'detroit')
        make_model: Search term - either "truck" for general search or "make+model" for specific (e.g., "nissan+frontier")
    """
    listings = []
    
    # Build search URL
    search_url = (
        f"https://{region}.craigslist.org/search/cta"
        f"?auto_make_model={make_model}"
        f"&min_auto_year={MIN_YEAR}"
        f"&max_auto_year={CURRENT_YEAR}"
        f"&search_distance=100"
        f"&postal=48176"
    )
    
    search_label = make_model.replace('+', ' ').title() if '+' in make_model else 'general trucks'
    logger.info(f"Scraping Craigslist {region} for {search_label}...")
    html = fetch_craigslist_html(region, search_url)
    
    if not html:
        return listings
    
    # Find all listing items
    item_pattern = r'<li class="cl-static-search-result"[^>]*>.*?</li>'
    items = re.findall(item_pattern, html, re.DOTALL)
    
    logger.info(f"Found {len(items)} potential listings in {region} for {search_label}")
    
    for item_html in items:
        listing = parse_craigslist_listing(item_html, region)
        if listing:
            listings.append(listing)
    
    logger.info(f"Parsed {len(listings)} valid listings from {region} for {search_label}")
    return listings


def scrape_craigslist() -> List[TruckListing]:
    """
    Scrape all Craigslist regions with both generic truck search and specific model searches
    Uses deduplication to handle listings that appear in multiple searches
    """
    all_listings = []
    seen_ids = set()  # Track unique listings by source_id
    
    # First, do generic truck search across all regions
    logger.info("=== Phase 1: Generic truck search ===")
    for region in CRAIGSLIST_REGIONS:
        regional_listings = scrape_craigslist_region(region, make_model="truck")
        for listing in regional_listings:
            if listing.source_id not in seen_ids:
                all_listings.append(listing)
                seen_ids.add(listing.source_id)
    
    logger.info(f"Generic truck search: {len(all_listings)} unique listings found")
    
    # Second, do specific model searches across all regions
    logger.info("=== Phase 2: Model-specific searches ===")
    model_specific_count = 0
    for make, model in SPECIFIC_TRUCK_MODELS:
        make_model_query = f"{make}+{model}"
        for region in CRAIGSLIST_REGIONS:
            regional_listings = scrape_craigslist_region(region, make_model=make_model_query)
            for listing in regional_listings:
                if listing.source_id not in seen_ids:
                    all_listings.append(listing)
                    seen_ids.add(listing.source_id)
                    model_specific_count += 1
    
    logger.info(f"Model-specific searches: {model_specific_count} additional unique listings found")
    logger.info(f"Total Craigslist listings collected: {len(all_listings)}")
    return all_listings


# ============================================================================
# FACEBOOK MARKETPLACE SCRAPER
# ============================================================================

def scrape_facebook_marketplace(browser_tool=None) -> List[TruckListing]:
    """
    Scrape Facebook Marketplace using browser automation
    Returns list of TruckListing objects
    browser_tool: callable that accepts dict params for browser operations
    """
    if not browser_tool:
        logger.warning("No browser tool provided for Facebook scraping")
        return []
    listings = []
    
    logger.info("Scraping Facebook Marketplace...")
    logger.info(f"URL: {FACEBOOK_MARKETPLACE_URL}")
    
    try:
        # Open Facebook Marketplace
        logger.info("Opening Facebook Marketplace page...")
        open_result = browser_tool({
            'action': 'open',
            'targetUrl': FACEBOOK_MARKETPLACE_URL,
            'profile': 'openclaw'
        })
        
        if not open_result or 'targetId' not in open_result:
            logger.error("Failed to open Facebook Marketplace")
            return listings
        
        target_id = open_result['targetId']
        
        # Wait for page to load
        import time
        time.sleep(5)
        
        # Take snapshot to see what's on the page
        logger.info("Taking page snapshot...")
        snapshot = browser_tool({
            'action': 'snapshot',
            'targetId': target_id,
            'refs': 'aria'
        })
        
        if not snapshot or 'snapshot' not in snapshot:
            logger.error("Failed to get page snapshot")
            return listings
        
        # Parse the snapshot to extract listings
        # Facebook Marketplace structure varies, but typically:
        # - Listings are in a grid/list format
        # - Each listing has: image, title, price, location
        
        snapshot_text = snapshot.get('snapshot', '')
        logger.info(f"Snapshot length: {len(snapshot_text)} characters")
        
        # Try to find listing links in the snapshot
        # Facebook listings typically have URLs like:
        # /marketplace/item/ITEM_ID/
        
        fb_listing_pattern = r'/marketplace/item/(\d+)/?'
        listing_ids = re.findall(fb_listing_pattern, snapshot_text)
        unique_ids = list(set(listing_ids))
        
        logger.info(f"Found {len(unique_ids)} unique Facebook listing IDs")
        
        # For each listing, try to extract details
        # This is simplified - in practice, we'd need to click each listing
        # or parse the snapshot more carefully
        
        # For now, let's try to extract what we can from the snapshot
        # by looking for price patterns and titles near listing links
        
        lines = snapshot_text.split('\n')
        current_listing = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for price patterns
            price_match = re.search(r'\$([0-9,]+)', line)
            if price_match:
                price = parse_craigslist_price(price_match.group(0))
                
                # Look for title in nearby lines
                title = None
                for j in range(max(0, i-3), min(len(lines), i+3)):
                    potential_title = lines[j].strip()
                    if len(potential_title) > 10 and not potential_title.startswith('$'):
                        # Check if it looks like a vehicle title
                        if any(make in potential_title.lower() for make in TRUCK_MAKES):
                            title = potential_title
                            break
                
                if title and price:
                    # Try to find listing ID
                    listing_id = None
                    for j in range(max(0, i-5), min(len(lines), i+5)):
                        id_match = re.search(fb_listing_pattern, lines[j])
                        if id_match:
                            listing_id = id_match.group(1)
                            break
                    
                    if not listing_id:
                        # Generate ID from title + price
                        listing_id = hashlib.md5(f"{title}{price}".encode()).hexdigest()[:12]
                    
                    # Parse vehicle details
                    year = extract_year(title)
                    make, model = extract_make_model(title)
                    mileage = parse_mileage(title)
                    
                    # Look for location
                    location = None
                    for j in range(i, min(len(lines), i+5)):
                        if 'mi' in lines[j] or 'miles' in lines[j] or any(city in lines[j].lower() for city in ['ann arbor', 'detroit', 'saline']):
                            location = lines[j].strip()
                            break
                    
                    listing = TruckListing(
                        source='facebook',
                        source_id=listing_id,
                        title=title,
                        price=price,
                        year=year,
                        make=make,
                        model=model,
                        mileage=mileage,
                        location=location,
                        url=f"https://www.facebook.com/marketplace/item/{listing_id}/"
                    )
                    
                    # Avoid duplicates in this session
                    if not any(l.title == listing.title and l.price == listing.price for l in listings):
                        listings.append(listing)
        
        logger.info(f"Extracted {len(listings)} listings from Facebook Marketplace")
        
    except Exception as e:
        logger.error(f"Error scraping Facebook Marketplace: {e}", exc_info=True)
    
    return listings


# ============================================================================
# FACEBOOK MARKETPLACE SCRAPER
# ============================================================================

def extract_facebook_listing_data(item_html: str) -> Optional[TruckListing]:
    """
    Parse a single Facebook Marketplace listing from HTML
    Facebook Marketplace listings are dynamically loaded, so this handles
    the structure once items are rendered.
    """
    try:
        # Extract title - usually in heading or link text
        title_match = re.search(r'<[a-z]+[^>]*>([^<]*(?:20\d{2}|truck|Truck)[^<]*)</[a-z]+>', item_html)
        title = None
        
        # Alternative: look for price pattern followed by title
        if not title_match:
            # Look for common truck/year patterns
            title_match = re.search(r'(?:20\d{2}|truck|Truck)[^$]*', item_html)
            if title_match:
                title = title_match.group(0).strip()
                # Clean up
                title = re.sub(r'<[^>]+>', '', title)[:100]
        else:
            title = title_match.group(1).strip()
        
        if not title:
            return None
        
        # Extract price - look for $ symbol followed by digits
        price_match = re.search(r'\$[\s,]*(\d{1,3}(?:[,]\d{3})*)', item_html)
        price = parse_craigslist_price(price_match.group(0)) if price_match else None
        
        # Extract Facebook listing URL/ID
        url_match = re.search(r'href="(/marketplace/item/(\d+)/?[^"]*)"', item_html)
        if not url_match:
            url_match = re.search(r'/marketplace/item/(\d+)', item_html)
            if url_match:
                listing_id = url_match.group(1)
                url = f"https://www.facebook.com/marketplace/item/{listing_id}/"
            else:
                return None
        else:
            url = f"https://www.facebook.com{url_match.group(1)}"
            listing_id = url_match.group(2)
        
        if not listing_id:
            return None
        
        # Extract description/notes
        description = ""
        desc_patterns = [
            r'(?:Details?|Description?)[:\s]*([^<]*(?:<br>|</[a-z]+>))',
            r'<p[^>]*>([^<]*truck[^<]*)</p>',
            r'<div[^>]*class="[^"]*description[^"]*"[^>]*>([^<]+)</div>',
        ]
        
        for pattern in desc_patterns:
            desc_match = re.search(pattern, item_html, re.IGNORECASE | re.DOTALL)
            if desc_match:
                description = desc_match.group(1).strip()
                if description:
                    break
        
        # Extract location (usually at bottom of listing)
        location_match = re.search(r'(?:Location|Address)[:\s]*([^<,\n]+)', item_html, re.IGNORECASE)
        location = location_match.group(1).strip() if location_match else None
        
        # Parse year, make, model from title
        year = extract_year(title)
        make, model = extract_make_model(title)
        
        # Parse mileage from description
        mileage = parse_mileage(description) if description else None
        
        # Create listing object with detailed description
        listing = TruckListing(
            source='facebook',
            source_id=listing_id,
            title=title,
            price=price,
            year=year,
            make=make,
            model=model,
            mileage=mileage,
            location=location,
            url=url,
            description=description,  # Include full description
        )
        
        return listing
    except Exception as e:
        logger.debug(f"Error parsing Facebook listing: {e}")
        return None


def extract_seller_info(description: str) -> Dict[str, str]:
    """
    Extract detailed seller information from listing description
    Looks for: condition, maintenance, issues, service records, notes
    """
    info = {
        'condition': None,
        'maintenance': [],
        'issues': [],
        'service_records': [],
        'seller_notes': description,
    }
    
    if not description:
        return info
    
    desc_lower = description.lower()
    
    # Condition assessment
    condition_patterns = [
        (r'\b(excellent|like new|mint|pristine|immaculate)\b', 'excellent'),
        (r'\b(very good|great|clean|well maintained)\b', 'very good'),
        (r'\b(good|nice|solid)\b', 'good'),
        (r'\b(fair|average|okay|needs work)\b', 'fair'),
        (r'\b(poor|rough|rough around edges|project)\b', 'poor'),
    ]
    
    for pattern, condition in condition_patterns:
        if re.search(pattern, desc_lower):
            info['condition'] = condition
            break
    
    # Maintenance items (positive indicators)
    maintenance_items = [
        'new tires', 'new brakes', 'new battery', 'new transmission',
        'new engine', 'fresh paint', 'new oil', 'oil changes',
        'service records', 'receipts', 'dealer maintained', 'well maintained',
        'recent service', 'just serviced', 'tune up', 'inspection',
        'timing belt', 'spark plugs', 'air filter', 'fuel filter',
        'fluids changed', 'maintenance records', 'full service history'
    ]
    
    for item in maintenance_items:
        if item in desc_lower:
            info['maintenance'].append(item)
    
    # Issues/damage (negative indicators)
    issue_patterns = [
        'rust', 'dent', 'scratch', 'crack', 'damage',
        'accident', 'salvage', 'rebuilt title', 'flood',
        'mechanical issue', 'transmission issue', 'engine issue',
        'no title', 'bad transmission', 'bad engine', 'bad brakes',
        'check engine', 'warning light', 'needs repair', 'needs work',
        'missing', 'broken', 'not working'
    ]
    
    for issue in issue_patterns:
        if issue in desc_lower:
            info['issues'].append(issue)
    
    # Service records indicators
    service_indicators = [
        'carfax', 'autocheck', 'service records', 'receipts',
        'maintenance history', 'dealer service', 'one owner',
        'clean title'
    ]
    
    for indicator in service_indicators:
        if indicator in desc_lower:
            info['service_records'].append(indicator)
    
    return info


def process_facebook_listing(listing: TruckListing) -> TruckListing:
    """
    Post-process Facebook listing to extract detailed seller information
    """
    if listing.description:
        seller_info = extract_seller_info(listing.description)
        
        # Add to description if not already present
        if seller_info['condition'] and 'condition:' not in listing.description.lower():
            listing.condition = seller_info['condition']
        
        # Enhance description with structured data
        if seller_info['maintenance'] or seller_info['issues'] or seller_info['service_records']:
            enhanced = f"{listing.description}\n\n[SELLER INFO]\n"
            
            if seller_info['condition']:
                enhanced += f"Condition: {seller_info['condition']}\n"
            
            if seller_info['maintenance']:
                enhanced += f"Maintenance: {', '.join(seller_info['maintenance'])}\n"
            
            if seller_info['service_records']:
                enhanced += f"Service: {', '.join(seller_info['service_records'])}\n"
            
            if seller_info['issues']:
                enhanced += f"Issues: {', '.join(seller_info['issues'])}\n"
            
            listing.description = enhanced
    
    return listing


# ============================================================================
# PARSING UTILITIES
# ============================================================================

def extract_year(text: str) -> Optional[int]:
    """Extract year from text"""
    match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
    if match:
        year = int(match.group(1))
        if MIN_YEAR <= year <= CURRENT_YEAR:
            return year
    return None


def extract_make_model(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract make and model from text"""
    text_lower = text.lower()
    make = None
    model = None
    
    # Find make
    for truck_make in sorted(TRUCK_MAKES, key=len, reverse=True):
        if truck_make in text_lower:
            make = truck_make.title()
            if make == 'Chevy':
                make = 'Chevrolet'
            break
    
    # Find model
    for truck_model in sorted(TRUCK_MODELS, key=len, reverse=True):
        if truck_model in text_lower:
            model = truck_model.upper()
            break
    
    return make, model


def parse_mileage(text: str) -> Optional[int]:
    """Parse mileage from text"""
    if not text:
        return None
    
    # Look for patterns
    match = re.search(r'(\d+[,.]?\d*)\s*[kmKM]*\s*miles?', text, re.IGNORECASE)
    if match:
        num_str = match.group(1).replace(',', '').replace('.', '')
        try:
            mileage = int(num_str)
            # If it's a small number with K/k, multiply by 1000
            if mileage < 1000 and 'k' in text.lower()[match.start():match.end()]:
                mileage *= 1000
            return mileage
        except ValueError:
            pass
    
    return None


# ============================================================================
# DEDUPLICATION & DATABASE OPERATIONS
# ============================================================================

def find_duplicate_in_db(conn, listing: TruckListing) -> Optional[str]:
    """
    Find if this listing already exists in the database
    Uses multiple strategies:
    1. Exact source_id match
    2. Dedup hash match (for cross-source duplicates)
    3. Fuzzy match on key fields
    """
    cursor = conn.cursor()
    
    # Strategy 1: Exact match on source_id
    cursor.execute("SELECT id FROM listings WHERE id = ?", (listing.db_id,))
    if cursor.fetchone():
        return listing.db_id
    
    # Strategy 2: Dedup hash match (cross-source duplicates)
    dedup_hash = listing.get_dedup_key()
    cursor.execute(
        "SELECT id FROM listings WHERE dedup_hash = ? AND id != ?",
        (dedup_hash, listing.db_id)
    )
    existing = cursor.fetchone()
    if existing:
        logger.info(f"Found cross-source duplicate via hash: {existing[0]}")
        return existing[0]
    
    # Strategy 3: Fuzzy match on year/make/model/price within 24 hours
    if listing.price and listing.year and listing.make and listing.model:
        # Look for same vehicle with similar price (within 5%)
        price_lower = listing.price * 0.95
        price_upper = listing.price * 1.05
        
        cursor.execute("""
            SELECT id FROM listings 
            WHERE year = ? 
            AND make = ? 
            AND model = ?
            AND price BETWEEN ? AND ?
            AND datetime(last_seen_date) > datetime('now', '-1 day')
            LIMIT 1
        """, (listing.year, listing.make, listing.model, price_lower, price_upper))
        
        existing = cursor.fetchone()
        if existing:
            logger.info(f"Found fuzzy duplicate: {existing[0]}")
            return existing[0]
    
    return None


def upsert_listing(conn, listing: TruckListing) -> Tuple[bool, str]:
    """
    Insert or update a listing. Returns (is_new, listing_id)
    """
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    # Check for duplicates
    existing_id = find_duplicate_in_db(conn, listing)
    
    # Compute derived fields
    price_per_mile = None
    if listing.price and listing.mileage and listing.mileage > 0:
        price_per_mile = listing.price / listing.mileage
    
    vehicle_age = None
    if listing.year:
        vehicle_age = CURRENT_YEAR - listing.year
    
    dedup_hash = listing.get_dedup_key()
    
    if existing_id:
        # Update existing
        cursor.execute("""
            UPDATE listings SET
                last_seen_date = ?,
                status = 'active',
                times_seen = times_seen + 1,
                price = ?,
                mileage = ?,
                title = ?,
                location = ?,
                description = ?,
                primary_image_url = ?,
                price_per_mile = ?,
                vehicle_condition_notes = ?,
                maintenance_history = ?,
                known_issues = ?,
                service_records = ?,
                seller_notes = ?,
                dedup_hash = ?,
                updated_at = ?
            WHERE id = ?
        """, (now, listing.price, listing.mileage, listing.title, listing.location or 'Unknown',
              listing.description, listing.primary_image_url, price_per_mile,
              listing.vehicle_condition_notes, listing.maintenance_history,
              listing.known_issues, listing.service_records, listing.seller_notes,
              dedup_hash, now, existing_id))
        
        # Track price change
        cursor.execute("SELECT price FROM listings WHERE id = ?", (existing_id,))
        row = cursor.fetchone()
        existing_price = row[0] if row else None
        
        if listing.price and existing_price and listing.price != existing_price:
            cursor.execute("""
                INSERT INTO price_history (listing_id, price, observed_date)
                VALUES (?, ?, ?)
            """, (existing_id, listing.price, now))
        
        conn.commit()
        return False, existing_id
    
    else:
        # Insert new
        try:
            cursor.execute("""
                INSERT INTO listings (
                    id, source, year, make, model,
                    price, mileage, location,
                    title, primary_image_url, image_count,
                    first_seen_date, last_seen_date, status, times_seen,
                    fb_url, price_per_mile, vehicle_age,
                    description, vehicle_condition_notes, maintenance_history,
                    known_issues, service_records, seller_notes, dedup_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing.db_id, listing.source, listing.year, listing.make, listing.model,
                listing.price or 0, listing.mileage, listing.location or 'Unknown',
                listing.title, listing.primary_image_url, len(listing.image_urls),
                now, now, 'active', 1,
                listing.url, price_per_mile, vehicle_age,
                listing.description, listing.vehicle_condition_notes, listing.maintenance_history,
                listing.known_issues, listing.service_records, listing.seller_notes, dedup_hash,
                now, now
            ))
            
            # Add initial price to history
            if listing.price:
                cursor.execute("""
                    INSERT INTO price_history (listing_id, price, observed_date)
                    VALUES (?, ?, ?)
                """, (listing.db_id, listing.price, now))
            
            conn.commit()
            logger.info(f"Inserted new listing: {listing.title} ({listing.source})")
            return True, listing.db_id
        
        except sqlite3.IntegrityError as e:
            logger.error(f"Error inserting listing: {e}")
            return False, listing.db_id


def mark_inactive_listings(conn, source: str, seen_ids: set) -> int:
    """Mark listings from a source that weren't seen as inactive"""
    yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat()
    cursor = conn.cursor()
    
    try:
        if seen_ids:
            placeholders = ','.join(['?' for _ in seen_ids])
            query = f"""
                UPDATE listings 
                SET status = 'inactive', updated_at = ?
                WHERE source = ?
                AND status = 'active' 
                AND last_seen_date < ?
                AND id NOT IN ({placeholders})
            """
            params = [datetime.utcnow().isoformat(), source, yesterday] + list(seen_ids)
        else:
            query = """
                UPDATE listings 
                SET status = 'inactive', updated_at = ?
                WHERE source = ?
                AND status = 'active' 
                AND last_seen_date < ?
            """
            params = [datetime.utcnow().isoformat(), source, yesterday]
        
        cursor.execute(query, params)
        inactive_count = cursor.rowcount
        conn.commit()
        return inactive_count
    except Exception as e:
        logger.error(f"Error marking inactive listings: {e}")
        return 0


def record_scrape_run(conn, source: str, stats: Dict) -> None:
    """Record stats about this scrape run"""
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO scrape_runs (
            run_date, listings_found, new_listings, inactive_listings,
            duration_seconds, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        stats.get('found', 0),
        stats.get('new', 0),
        stats.get('inactive', 0),
        stats.get('duration', 0),
        stats.get('status', 'success'),
        stats.get('error')
    ))
    conn.commit()


def get_db_stats() -> Dict:
    """Get current database statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total and active listings
    cursor.execute("SELECT COUNT(*) FROM listings WHERE status = 'active'")
    stats['active'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM listings")
    stats['total'] = cursor.fetchone()[0]
    
    # By source
    cursor.execute("""
        SELECT source, COUNT(*) as count
        FROM listings
        WHERE status = 'active'
        GROUP BY source
    """)
    stats['by_source'] = dict(cursor.fetchall())
    
    # Price stats
    cursor.execute("""
        SELECT MIN(price), MAX(price), AVG(price)
        FROM listings
        WHERE status = 'active' AND price IS NOT NULL AND price > 0
    """)
    row = cursor.fetchone()
    if row and row[0]:
        min_p, max_p, avg_p = row
        stats['price'] = {'min': min_p, 'max': max_p, 'avg': round(avg_p, 2) if avg_p else None}
    
    conn.close()
    return stats


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def run_scrape(browser_tool=None) -> Dict:
    """
    Run full scrape across all sources
    browser_tool: function to call browser operations (for Facebook)
    """
    import time
    
    # Initialize database first
    init_db()
    
    start_time = time.time()
    conn = get_connection()
    
    stats = {
        'total_found': 0,
        'total_new': 0,
        'total_inactive': 0,
        'by_source': {},
    }
    
    try:
        # === CRAIGSLIST ===
        logger.info("=" * 60)
        logger.info("Starting Craigslist scrape...")
        logger.info("=" * 60)
        
        craigslist_listings = scrape_craigslist()
        stats['by_source']['craigslist'] = {
            'found': len(craigslist_listings),
            'new': 0,
            'inactive': 0
        }
        
        seen_craigslist_ids = set()
        
        for listing in craigslist_listings:
            is_new, listing_id = upsert_listing(conn, listing)
            if is_new:
                stats['by_source']['craigslist']['new'] += 1
            seen_craigslist_ids.add(listing_id)
            stats['total_found'] += 1
            stats['total_new'] += (1 if is_new else 0)
        
        # Mark inactive
        inactive = mark_inactive_listings(conn, 'craigslist', seen_craigslist_ids)
        stats['by_source']['craigslist']['inactive'] = inactive
        stats['total_inactive'] += inactive
        
        # === FACEBOOK MARKETPLACE ===
        if browser_tool:
            logger.info("=" * 60)
            logger.info("Starting Facebook Marketplace scrape...")
            logger.info("=" * 60)
            
            fb_listings = scrape_facebook_marketplace(browser_tool)
            stats['by_source']['facebook'] = {
                'found': len(fb_listings),
                'new': 0,
                'inactive': 0
            }
            
            seen_fb_ids = set()
            
            for listing in fb_listings:
                is_new, listing_id = upsert_listing(conn, listing)
                if is_new:
                    stats['by_source']['facebook']['new'] += 1
                seen_fb_ids.add(listing_id)
                stats['total_found'] += 1
                stats['total_new'] += (1 if is_new else 0)
            
            # Mark inactive
            inactive = mark_inactive_listings(conn, 'facebook', seen_fb_ids)
            stats['by_source']['facebook']['inactive'] = inactive
            stats['total_inactive'] += inactive
        else:
            logger.warning("Browser tool not provided - skipping Facebook Marketplace")
        
        duration = time.time() - start_time
        
        # Record scrape run
        record_scrape_run(conn, 'all', {
            'found': stats['total_found'],
            'new': stats['total_new'],
            'inactive': stats['total_inactive'],
            'duration': duration,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Scrape failed: {e}", exc_info=True)
        stats['error'] = str(e)
        record_scrape_run(conn, 'all', {
            'status': 'failed',
            'error': str(e),
            'duration': time.time() - start_time
        })
    
    finally:
        conn.close()
    
    return stats


if __name__ == '__main__':
    import sys
    
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")
    
    # For standalone testing, run without browser
    logger.info("Starting scrape...")
    stats = run_scrape(browser_tool=None)
    
    # Print results
    print("\n" + "=" * 70)
    print("SCRAPE RESULTS")
    print("=" * 70)
    
    print(f"\nTotal listings found: {stats['total_found']}")
    print(f"New listings added: {stats['total_new']}")
    print(f"Listings marked inactive: {stats['total_inactive']}")
    
    if stats.get('by_source'):
        print("\nBy Source:")
        for source, source_stats in stats['by_source'].items():
            print(f"  {source.title()}: {source_stats['found']} found, {source_stats['new']} new, {source_stats['inactive']} inactive")
    
    # Get current database stats
    db_stats = get_db_stats()
    print("\nDatabase Stats:")
    print(f"  Total listings: {db_stats['total']}")
    print(f"  Active listings: {db_stats['active']}")
    if db_stats.get('by_source'):
        for source, count in db_stats['by_source'].items():
            print(f"    - {source.title()}: {count}")
    
    if db_stats.get('price'):
        price_range = db_stats['price']
        if price_range.get('avg'):
            print(f"  Price range: ${price_range['min']:,} - ${price_range['max']:,}")
            print(f"  Average price: ${price_range['avg']:,.2f}")
    
    print("\n" + "=" * 70)
    
    if stats.get('error'):
        print(f"Error: {stats['error']}")
        sys.exit(1)
