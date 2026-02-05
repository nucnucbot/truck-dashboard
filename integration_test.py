#!/usr/bin/env python3
"""
Integration test for multi-source truck scraper
This script will be called from OpenClaw with real browser tool
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import scraper


def create_browser_wrapper(browser_func):
    """
    Create a wrapper around OpenClaw browser function
    """
    def browser_tool(params):
        """Wrapper that calls the actual OpenClaw browser function"""
        return browser_func(params)
    
    return browser_tool


def main(browser_func=None):
    """
    Run comprehensive multi-source scrape
    browser_func: Optional browser function from OpenClaw
    """
    
    print("\n" + "=" * 70)
    print("MULTI-SOURCE TRUCK MARKET SCRAPER")
    print("Saline, MI Area - Trucks <15 Years Old")
    print("=" * 70)
    
    # Initialize database
    print("\n[1/3] Initializing database...")
    scraper.init_db()
    print("✓ Database initialized with schema")
    
    # Create browser wrapper if provided
    browser_tool = create_browser_wrapper(browser_func) if browser_func else None
    
    # Run scrape
    print("\n[2/3] Running multi-source scrape...")
    print("-" * 70)
    
    stats = scraper.run_scrape(browser_tool=browser_tool)
    
    # Print results
    print("\n[3/3] Scrape Results")
    print("=" * 70)
    
    print(f"\n📊 Overall Statistics:")
    print(f"  Total listings found: {stats['total_found']}")
    print(f"  New listings added: {stats['total_new']}")
    print(f"  Listings marked inactive: {stats['total_inactive']}")
    
    if stats.get('by_source'):
        print(f"\n📁 By Source:")
        for source, source_stats in stats['by_source'].items():
            print(f"\n  {source.upper()}:")
            print(f"    Found: {source_stats['found']}")
            print(f"    New: {source_stats['new']}")
            print(f"    Updated: {source_stats['found'] - source_stats['new']}")
            print(f"    Marked Inactive: {source_stats['inactive']}")
    
    # Get current database stats
    print("\n" + "=" * 70)
    print("DATABASE STATISTICS")
    print("=" * 70)
    
    db_stats = scraper.get_db_stats()
    print(f"\n📈 Current Database State:")
    print(f"  Total listings (all-time): {db_stats['total']}")
    print(f"  Active listings: {db_stats['active']}")
    print(f"  Inactive listings: {db_stats['total'] - db_stats['active']}")
    
    if db_stats.get('by_source'):
        print(f"\n📌 Active Listings by Source:")
        for source, count in sorted(db_stats['by_source'].items()):
            percentage = (count / db_stats['active'] * 100) if db_stats['active'] > 0 else 0
            print(f"  {source.capitalize():15} {count:4} ({percentage:.1f}%)")
    
    if db_stats.get('price'):
        price_range = db_stats['price']
        if price_range.get('avg'):
            print(f"\n💰 Price Statistics:")
            print(f"  Minimum: ${price_range['min']:,}")
            print(f"  Maximum: ${price_range['max']:,}")
            print(f"  Average: ${price_range['avg']:,.2f}")
    
    # Sample listings
    print("\n" + "=" * 70)
    print("SAMPLE LISTINGS (Newest)")
    print("=" * 70)
    
    conn = scraper.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT year, make, model, price, mileage, location, source
        FROM listings
        WHERE status = 'active'
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    
    if rows:
        print()
        for i, row in enumerate(rows, 1):
            year, make, model, price, mileage, location, source = row
            vehicle_str = f"{year} {make} {model}" if year and make and model else "Unknown Vehicle"
            price_str = f"${price:,}" if price and price > 0 else "Price N/A"
            mileage_str = f"{mileage:,} mi" if mileage else "Mileage N/A"
            
            print(f"{i:2}. {vehicle_str:30} {price_str:12} {mileage_str:15} [{source}]")
            print(f"    Location: {location}")
    
    conn.close()
    
    print("\n" + "=" * 70)
    
    if stats.get('error'):
        print(f"\n⚠️  Error occurred: {stats['error']}")
        return 1
    
    print(f"\n✅ Scrape completed successfully!")
    print(f"   Database: {Path(scraper.DB_PATH).absolute()}")
    
    return 0


if __name__ == '__main__':
    # Run with no browser (Craigslist only)
    sys.exit(main())
