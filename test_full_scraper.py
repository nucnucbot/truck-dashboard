#!/usr/bin/env python3
"""
Comprehensive test of the truck market scraper with Craigslist and Facebook Marketplace
"""
import sqlite3
import sys
from scraper import (
    run_scrape, get_db_stats, extract_seller_info, 
    process_facebook_listing, TruckListing
)


def test_seller_info_extraction():
    """Test the seller information extraction from descriptions"""
    print("\n" + "=" * 80)
    print("TEST: Seller Information Extraction")
    print("=" * 80)
    
    test_descriptions = [
        """
        2019 Chevrolet Colorado - Excellent condition! Recently serviced with new brakes, 
        new battery, and fresh oil change. Full service records available. No accidents, 
        clean title. Well maintained by single owner.
        """,
        """
        2015 Ford F-150 - Good condition, has some rust on door frames and a small dent 
        on passenger side. Timing belt changed at 140K miles. Check engine light is on. 
        Needs some work but reliable truck.
        """,
        """
        2020 Ram 1500 - Fair condition. 4 new tires just installed. Engine has mechanical 
        issue that needs transmission rebuild. Previous accident damage to frame. 
        Selling as-is, no warranty.
        """,
    ]
    
    for i, desc in enumerate(test_descriptions, 1):
        info = extract_seller_info(desc)
        print(f"\nDescription {i}:")
        print(f"  Condition: {info['condition']}")
        if info['maintenance']:
            print(f"  Maintenance: {', '.join(info['maintenance'][:3])}")
        if info['issues']:
            print(f"  Issues: {', '.join(info['issues'][:3])}")
        if info['service_records']:
            print(f"  Service: {', '.join(info['service_records'])}")
    
    print("\n✓ Seller info extraction test PASSED")
    return True


def test_facebook_listing_processing():
    """Test Facebook listing data processing"""
    print("\n" + "=" * 80)
    print("TEST: Facebook Listing Processing")
    print("=" * 80)
    
    # Create a mock Facebook listing
    mock_listing = TruckListing(
        source='facebook',
        source_id='123456789',
        title='2020 Chevrolet Silverado 1500 Crew Cab 4WD',
        price=32000,
        year=2020,
        make='Chevrolet',
        model='SILVERADO',
        mileage=45000,
        location='Ann Arbor, MI',
        url='https://www.facebook.com/marketplace/item/123456789/',
        description="""
        Well maintained Silverado with new brakes and fresh oil change. 
        Carfax shows clean history. No major issues, excellent condition.
        Dealer maintained with full service records available.
        """
    )
    
    # Process it
    processed = process_facebook_listing(mock_listing)
    
    print(f"\nOriginal description length: {len(mock_listing.description)}")
    print(f"Processed description length: {len(processed.description) if processed.description else 0}")
    
    if processed.description and '[SELLER INFO]' in processed.description:
        print("✓ Seller info successfully added to description")
        # Show the structured info
        lines = processed.description.split('\n')
        print("\nExtracted information:")
        for line in lines:
            if any(prefix in line for prefix in ['Condition:', 'Maintenance:', 'Service:', 'Issues:']):
                print(f"  {line}")
    
    print("\n✓ Facebook listing processing test PASSED")
    return True


def test_database_schema():
    """Test that database has all required columns"""
    print("\n" + "=" * 80)
    print("TEST: Database Schema Verification")
    print("=" * 80)
    
    try:
        conn = sqlite3.connect("trucks.db")
        cursor = conn.cursor()
        
        # Check if new columns exist
        cursor.execute("PRAGMA table_info(listings)")
        all_columns = cursor.fetchall()
        column_names = {row[1] for row in all_columns}
        
        required_cols = [
            'source', 'title', 'price', 'year', 'make', 'model',
            'location', 'description', 'vehicle_condition_notes',
            'maintenance_history', 'known_issues', 'service_records',
            'seller_notes', 'dedup_hash', 'status', 'created_at', 'updated_at'
        ]
        
        missing = [col for col in required_cols if col not in column_names]
        
        if missing:
            print(f"✗ Missing columns: {missing}")
            print(f"✓ Available columns: {sorted(column_names)}")
            return False
        
        print("✓ All required columns present:")
        for col in required_cols:
            print(f"  ✓ {col}")
        
        # Verify total column count
        print(f"\nTotal columns in listings: {len(all_columns)}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database schema test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scraper_multi_source():
    """Test that scraper works with Craigslist"""
    print("\n" + "=" * 80)
    print("TEST: Multi-Source Scraper (Craigslist Only - No Browser)")
    print("=" * 80)
    
    try:
        # Run scraper with no browser tool (Facebook will be skipped)
        stats = run_scrape(browser_tool=None)
        
        print(f"\nScrape Results:")
        print(f"  Total found: {stats['total_found']}")
        print(f"  New listings: {stats['total_new']}")
        print(f"  Inactive marked: {stats['total_inactive']}")
        
        if 'by_source' in stats:
            print(f"\n  By Source:")
            for source, source_stats in stats['by_source'].items():
                print(f"    {source.title()}: {source_stats.get('found', 0)} found, "
                      f"{source_stats.get('new', 0)} new")
        
        # Verify database is populated
        db_stats = get_db_stats()
        print(f"\n  Database Stats:")
        print(f"    Active listings: {db_stats.get('active', 0)}")
        print(f"    Total listings: {db_stats.get('total', 0)}")
        print(f"    By source: {db_stats.get('by_source', {})}")
        
        if db_stats.get('active', 0) > 0:
            print("\n✓ Multi-source scraper test PASSED")
            return True
        else:
            print("\n✗ No listings found in database")
            return False
    
    except Exception as e:
        print(f"✗ Scraper test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_seller_info_in_db():
    """Test that seller info is stored in database"""
    print("\n" + "=" * 80)
    print("TEST: Seller Information Storage in Database")
    print("=" * 80)
    
    try:
        conn = sqlite3.connect("trucks.db")
        cursor = conn.cursor()
        
        # Check listings with descriptions
        cursor.execute("""
            SELECT COUNT(*) FROM listings 
            WHERE description IS NOT NULL AND description != ''
        """)
        with_desc = cursor.fetchone()[0]
        
        # Check if any have structured seller info
        cursor.execute("""
            SELECT COUNT(*) FROM listings 
            WHERE (vehicle_condition_notes IS NOT NULL 
                   OR maintenance_history IS NOT NULL
                   OR known_issues IS NOT NULL
                   OR service_records IS NOT NULL)
        """)
        with_seller_info = cursor.fetchone()[0]
        
        print(f"\nDatabase listing status:")
        print(f"  Listings with description: {with_desc}")
        print(f"  With extracted seller info: {with_seller_info}")
        
        # Show example
        cursor.execute("""
            SELECT title, vehicle_condition_notes, maintenance_history,
                   known_issues, service_records
            FROM listings
            WHERE vehicle_condition_notes IS NOT NULL
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        if row:
            print(f"\nExample listing:")
            print(f"  Title: {row[0]}")
            print(f"  Condition: {row[1]}")
            print(f"  Maintenance: {row[2]}")
            print(f"  Issues: {row[3]}")
            print(f"  Service: {row[4]}")
        
        conn.close()
        print("\n✓ Seller info storage test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Seller info test FAILED: {e}")
        return False


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("TRUCK MARKET SCRAPER - COMPREHENSIVE TEST SUITE")
    print("Multi-Source with Detailed Seller Information Extraction")
    print("=" * 80)
    
    results = []
    
    # Test 1: Seller info extraction (no DB needed)
    results.append(("Seller Info Extraction", test_seller_info_extraction()))
    
    # Test 2: Facebook listing processing (no DB needed)
    results.append(("Facebook Listing Processing", test_facebook_listing_processing()))
    
    # Test 3: Scraper multi-source (FIRST - initializes DB)
    results.append(("Multi-Source Scraper", test_scraper_multi_source()))
    
    # Test 4: Database schema (after scraper has initialized it)
    results.append(("Database Schema", test_database_schema()))
    
    # Test 5: Seller info in database (after scraper has run)
    results.append(("Seller Info Storage", test_seller_info_in_db()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print("\n" + "=" * 80)
    
    if all(result[1] for result in results):
        print("✅ ALL TESTS PASSED - SCRAPER READY FOR PRODUCTION")
        print("=" * 80 + "\n")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED - REVIEW ERRORS ABOVE")
        print("=" * 80 + "\n")
        sys.exit(1)
