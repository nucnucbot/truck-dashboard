#!/usr/bin/env python3
"""
Live Facebook Marketplace test with real browser
This script is designed to be called from OpenClaw with browser tool access
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import scraper


def test_with_browser_tool(browser_func):
    """
    Test Facebook scraping with real browser
    browser_func: The actual browser tool function from OpenClaw
    """
    
    print("\n" + "=" * 70)
    print("LIVE FACEBOOK MARKETPLACE TEST")
    print("=" * 70)
    
    # Initialize database
    print("\nInitializing database...")
    scraper.init_db()
    print("✓ Database ready")
    
    # Create browser wrapper
    def browser_tool(params):
        return browser_func(params)
    
    # Run Facebook scraper
    print("\nScraping Facebook Marketplace...")
    print("URL:", scraper.FACEBOOK_MARKETPLACE_URL)
    print("-" * 70)
    
    listings = scraper.scrape_facebook_marketplace(browser_tool)
    
    print(f"\n✓ Scraping complete: Found {len(listings)} listings")
    
    # Display listings
    if listings:
        print("\n" + "=" * 70)
        print(f"EXTRACTED {len(listings)} FACEBOOK LISTINGS")
        print("=" * 70)
        
        for i, listing in enumerate(listings, 1):
            print(f"\n{i}. {listing.title}")
            print(f"   Price: ${listing.price:,}" if listing.price else "   Price: Not listed")
            print(f"   Year: {listing.year}" if listing.year else "   Year: Unknown")
            if listing.make:
                print(f"   Make: {listing.make}")
            if listing.model:
                print(f"   Model: {listing.model}")
            if listing.mileage:
                print(f"   Mileage: {listing.mileage:,} miles")
            if listing.location:
                print(f"   Location: {listing.location}")
            print(f"   URL: {listing.url}")
            print(f"   Source ID: {listing.source_id}")
        
        # Store in database
        print("\n" + "=" * 70)
        print("STORING IN DATABASE")
        print("=" * 70)
        
        conn = scraper.get_connection()
        new_count = 0
        update_count = 0
        
        for listing in listings:
            is_new, listing_id = scraper.upsert_listing(conn, listing)
            if is_new:
                new_count += 1
                print(f"✓ NEW: {listing.title}")
            else:
                update_count += 1
                print(f"↻ UPDATED: {listing.title}")
        
        conn.close()
        
        print(f"\n📊 Summary:")
        print(f"   New listings: {new_count}")
        print(f"   Updated listings: {update_count}")
        
        # Show database stats
        db_stats = scraper.get_db_stats()
        print(f"\n📈 Database Stats:")
        print(f"   Total active listings: {db_stats['active']}")
        if db_stats.get('by_source'):
            for source, count in db_stats['by_source'].items():
                print(f"     - {source}: {count}")
    
    else:
        print("\n⚠️  No listings found")
        print("   This could mean:")
        print("   - Facebook Marketplace page structure has changed")
        print("   - No listings matched the search criteria")
        print("   - Browser snapshot didn't load properly")
    
    print("\n" + "=" * 70)
    return 0


if __name__ == '__main__':
    print("\nThis script needs to be called from OpenClaw with browser tool access.")
    print("Use it like this in your OpenClaw agent:")
    print()
    print("```python")
    print("from truck_market import test_live_facebook")
    print("test_live_facebook.test_with_browser_tool(browser_tool)")
    print("```")
    print()
    sys.exit(1)
