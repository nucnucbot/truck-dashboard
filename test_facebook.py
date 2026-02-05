#!/usr/bin/env python3
"""
Test Facebook Marketplace scraping with real browser
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import scrape_facebook_marketplace, init_db, get_connection, upsert_listing


def browser_tool(params):
    """
    Mock browser tool for testing
    In actual usage, this will be called from OpenClaw with real browser
    """
    print(f"\n[Browser Tool Called]")
    print(f"  Action: {params['action']}")
    if 'targetUrl' in params:
        print(f"  URL: {params['targetUrl']}")
    
    # Return mock data for testing
    if params['action'] == 'open':
        return {
            'targetId': 'test_target_123',
            'url': params.get('targetUrl', '')
        }
    elif params['action'] == 'snapshot':
        # Simulate Facebook Marketplace snapshot
        return {
            'snapshot': '''
Facebook Marketplace - Trucks for Sale

2020 Ford F-150
$25,000
Ann Arbor, MI · 85,000 miles
/marketplace/item/1234567890/

2019 Chevrolet Silverado 1500
$28,500
Detroit, MI · 92,000 miles
/marketplace/item/2345678901/

2018 Ram 1500
$22,000
Saline, MI · 105,000 miles
/marketplace/item/3456789012/

2021 Toyota Tacoma
$32,000
Ypsilanti, MI · 45,000 miles
/marketplace/item/4567890123/

2017 GMC Sierra 1500
$19,500
Dexter, MI · 118,000 miles
/marketplace/item/5678901234/
            '''
        }
    
    return {}


def main():
    """Test Facebook Marketplace scraping"""
    
    print("=" * 70)
    print("FACEBOOK MARKETPLACE SCRAPER TEST")
    print("=" * 70)
    
    # Initialize database
    print("\nInitializing database...")
    init_db()
    
    # Test scraping
    print("\nTesting Facebook Marketplace scraper...")
    listings = scrape_facebook_marketplace(browser_tool)
    
    print(f"\n[Scraping Complete]")
    print(f"  Found {len(listings)} listings")
    
    # Display listings
    if listings:
        print("\n" + "=" * 70)
        print("EXTRACTED LISTINGS")
        print("=" * 70)
        
        for i, listing in enumerate(listings, 1):
            print(f"\n{i}. {listing.title}")
            print(f"   Price: ${listing.price:,}" if listing.price else "   Price: Unknown")
            print(f"   Year: {listing.year}" if listing.year else "   Year: Unknown")
            print(f"   Make: {listing.make}" if listing.make else "   Make: Unknown")
            print(f"   Model: {listing.model}" if listing.model else "   Model: Unknown")
            print(f"   Mileage: {listing.mileage:,}" if listing.mileage else "   Mileage: Unknown")
            print(f"   Location: {listing.location}" if listing.location else "   Location: Unknown")
            print(f"   URL: {listing.url}")
            print(f"   ID: {listing.db_id}")
        
        # Test database insertion
        print("\n" + "=" * 70)
        print("TESTING DATABASE INSERTION")
        print("=" * 70)
        
        conn = get_connection()
        new_count = 0
        update_count = 0
        
        for listing in listings:
            is_new, listing_id = upsert_listing(conn, listing)
            if is_new:
                new_count += 1
                print(f"✓ Inserted new: {listing.title}")
            else:
                update_count += 1
                print(f"↻ Updated existing: {listing.title}")
        
        conn.close()
        
        print(f"\nSummary:")
        print(f"  New listings: {new_count}")
        print(f"  Updated listings: {update_count}")
    
    else:
        print("\n⚠ No listings extracted")
    
    print("\n" + "=" * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
