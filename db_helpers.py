#!/usr/bin/env python3
"""
Database helper functions for truck market data
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any

DB_PATH = Path(__file__).parent / "trucks.db"


def get_connection():
    """Get a database connection"""
    return sqlite3.connect(DB_PATH)


def get_stats():
    """Get current database statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total listings
    cursor.execute("SELECT COUNT(*) FROM listings")
    stats['total_listings'] = cursor.fetchone()[0]
    
    # Active listings
    cursor.execute("SELECT COUNT(*) FROM listings WHERE status = 'active'")
    stats['active_listings'] = cursor.fetchone()[0]
    
    # Inactive listings
    cursor.execute("SELECT COUNT(*) FROM listings WHERE status = 'inactive'")
    stats['inactive_listings'] = cursor.fetchone()[0]
    
    # Price range
    cursor.execute("SELECT MIN(price), MAX(price), AVG(price) FROM listings WHERE status = 'active' AND price IS NOT NULL")
    min_price, max_price, avg_price = cursor.fetchone()
    stats['price_range'] = {
        'min': min_price,
        'max': max_price,
        'avg': round(avg_price, 2) if avg_price else None
    }
    
    # Total scrapes
    cursor.execute("SELECT COUNT(*) FROM scrape_runs")
    stats['total_scrapes'] = cursor.fetchone()[0]
    
    # Last scrape
    cursor.execute("SELECT run_date, listings_found, new_listings FROM scrape_runs ORDER BY run_date DESC LIMIT 1")
    last_scrape = cursor.fetchone()
    if last_scrape:
        stats['last_scrape'] = {
            'date': last_scrape[0],
            'found': last_scrape[1],
            'new': last_scrape[2]
        }
    
    conn.close()
    return stats


def get_best_deals(limit=10):
    """Get best value trucks (lowest price per mile)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT year, make, model, price, mileage, 
               ROUND(price_per_mile, 2) as ppm,
               location, fb_url
        FROM listings 
        WHERE status = 'active' 
          AND mileage > 0
          AND price_per_mile IS NOT NULL
        ORDER BY price_per_mile ASC
        LIMIT ?
    """, (limit,))
    
    deals = []
    for row in cursor.fetchall():
        deals.append({
            'year': row[0],
            'make': row[1],
            'model': row[2],
            'price': row[3],
            'mileage': row[4],
            'price_per_mile': row[5],
            'location': row[6],
            'url': row[7]
        })
    
    conn.close()
    return deals


def get_price_drops(limit=10):
    """Get listings with recent price drops"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT l.year, l.make, l.model, l.location,
               ph.price as old_price, l.price as current_price,
               (ph.price - l.price) as savings,
               l.fb_url
        FROM listings l
        JOIN (
            SELECT listing_id, MAX(observed_date) as last_change, price
            FROM price_history
            GROUP BY listing_id
        ) ph ON l.id = ph.listing_id
        WHERE l.status = 'active'
          AND ph.price > l.price
        ORDER BY savings DESC
        LIMIT ?
    """, (limit,))
    
    drops = []
    for row in cursor.fetchall():
        drops.append({
            'year': row[0],
            'make': row[1],
            'model': row[2],
            'location': row[3],
            'old_price': row[4],
            'current_price': row[5],
            'savings': row[6],
            'url': row[7]
        })
    
    conn.close()
    return drops


def get_make_model_stats():
    """Get aggregated stats by make and model"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT make, model, COUNT(*) as count,
               AVG(price) as avg_price,
               AVG(mileage) as avg_mileage,
               AVG(price_per_mile) as avg_ppm
        FROM listings
        WHERE status = 'active'
          AND make IS NOT NULL
          AND model IS NOT NULL
        GROUP BY make, model
        HAVING count >= 3
        ORDER BY count DESC
    """)
    
    stats = []
    for row in cursor.fetchall():
        stats.append({
            'make': row[0],
            'model': row[1],
            'count': row[2],
            'avg_price': round(row[3], 2) if row[3] else None,
            'avg_mileage': round(row[4], 2) if row[4] else None,
            'avg_price_per_mile': round(row[5], 2) if row[5] else None
        })
    
    conn.close()
    return stats


if __name__ == '__main__':
    # Quick stats check
    stats = get_stats()
    print("=== Truck Market Database Stats ===")
    print(f"Total listings: {stats['total_listings']}")
    print(f"Active: {stats['active_listings']}")
    print(f"Inactive: {stats['inactive_listings']}")
    
    if stats['price_range']['avg']:
        print(f"\nPrice range: ${stats['price_range']['min']:,} - ${stats['price_range']['max']:,}")
        print(f"Average: ${stats['price_range']['avg']:,.2f}")
    
    print(f"\nTotal scrapes: {stats['total_scrapes']}")
    
    if stats.get('last_scrape'):
        print(f"Last scrape: {stats['last_scrape']['date']}")
        print(f"  Found: {stats['last_scrape']['found']}")
        print(f"  New: {stats['last_scrape']['new']}")
