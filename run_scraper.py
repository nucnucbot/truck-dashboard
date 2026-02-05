#!/usr/bin/env python3
"""
Test runner for truck market scraper with browser integration
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import run_scrape, init_db, get_db_stats


class BrowserToolWrapper:
    """Wrapper to simulate browser tool calls from Python"""
    
    def __init__(self, actual_browser_func=None):
        self.actual_browser_func = actual_browser_func
    
    def __call__(self, params):
        """
        Call browser tool with params
        In actual usage, this would be provided by the OpenClaw runtime
        """
        if self.actual_browser_func:
            return self.actual_browser_func(params)
        else:
            # For standalone testing, return mock data
            print(f"[MOCK] Browser call: {params['action']}")
            
            if params['action'] == 'open':
                return {
                    'targetId': 'mock_target_123',
                    'url': params.get('targetUrl', '')
                }
            elif params['action'] == 'snapshot':
                # Return mock snapshot data
                return {
                    'snapshot': '''
                    2020 Ford F-150
                    $25,000
                    Ann Arbor, MI
                    /marketplace/item/1234567890/
                    
                    2019 Chevrolet Silverado
                    $28,500
                    Detroit, MI
                    /marketplace/item/2345678901/
                    
                    2018 Ram 1500
                    $22,000
                    Saline, MI
                    /marketplace/item/3456789012/
                    '''
                }
            
            return {}


def main():
    """Run the scraper with browser support"""
    
    # Initialize database
    print("Initializing database...")
    init_db()
    print("Database initialized\n")
    
    # Create browser tool wrapper
    # In OpenClaw runtime, this would be the actual browser function
    browser_tool = BrowserToolWrapper()
    
    # Run scrape
    print("Starting multi-source scrape...")
    print("=" * 70)
    
    stats = run_scrape(browser_tool=browser_tool)
    
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
            print(f"  {source.title()}:")
            print(f"    Found: {source_stats['found']}")
            print(f"    New: {source_stats['new']}")
            print(f"    Inactive: {source_stats['inactive']}")
    
    # Get current database stats
    print("\n" + "=" * 70)
    print("DATABASE STATISTICS")
    print("=" * 70)
    
    db_stats = get_db_stats()
    print(f"\nTotal listings in database: {db_stats['total']}")
    print(f"Active listings: {db_stats['active']}")
    
    if db_stats.get('by_source'):
        print("\nActive listings by source:")
        for source, count in db_stats['by_source'].items():
            print(f"  {source.title()}: {count}")
    
    if db_stats.get('price'):
        price_range = db_stats['price']
        if price_range.get('avg'):
            print(f"\nPrice statistics:")
            print(f"  Minimum: ${price_range['min']:,}")
            print(f"  Maximum: ${price_range['max']:,}")
            print(f"  Average: ${price_range['avg']:,.2f}")
    
    print("\n" + "=" * 70)
    
    if stats.get('error'):
        print(f"\nError occurred: {stats['error']}")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
