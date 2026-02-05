#!/usr/bin/env python3
"""
Process browser snapshot data and store listings
"""

import sys
import json
from datetime import datetime
from scraper import init_db, parse_listing, upsert_listing, mark_inactive_listings, record_scrape_run

# Truck listings extracted from snapshot
listings_data = [
    {"title": "2020 Ram lot of cars!!!", "price": "$2,000", "mileage": "123K miles", "location": "Toledo, OH", "url": "/marketplace/item/1253984123273381/"},
    {"title": "2016 Ford f-150 sport 4x4 2.7l v6 ecoboost", "price": "$18,000", "mileage": "96K miles", "location": "Royal Oak, MI", "url": "/marketplace/item/732906193001273/"},
    {"title": "2011 Ford f-250 Short Bed", "price": "$5,000", "mileage": "224K miles", "location": "Pinckney, MI", "url": "/marketplace/item/1392305779253014/"},
    {"title": "2012 Dodge ram 1500 SLT Pickup 2D 6 1/3 ft", "price": "$4,899", "mileage": "200K miles", "location": "Taylor, MI", "url": "/marketplace/item/1459873779475429/"},
    {"title": "2013 Dodge ram hemi big horn crew cab 4x4 full size 4-door pickup truck", "price": "$10,900", "mileage": "159K miles", "location": "Jackson, MI", "url": "/marketplace/item/872005735746642/"},
    {"title": "2011 Chevrolet avalanche LTZ Sport Utility Pickup 4D 5 1/4 ft", "price": "$10,900", "mileage": "189K miles", "location": "Adrian, MI", "url": "/marketplace/item/884531794356652/"},
    {"title": "2015 Ford f-150 FX2 Pickup 4D 5 1/2 ft", "price": "$5,500", "mileage": "159K miles", "location": "Detroit, MI", "url": "/marketplace/item/1543483900267925/"},
    {"title": "2017 GMC", "price": "$17,500", "mileage": "101K miles", "location": "Toledo, OH", "url": "/marketplace/item/25228240716851278/"},
    {"title": "2016 Ford f-150", "price": "$17,870", "mileage": "135K miles", "location": "Wayne, MI", "url": "/marketplace/item/1296282482307294/"},
    {"title": "2021 Chevrolet silverado 1500 lt trail boss", "price": "$28,488", "mileage": "103K miles", "location": "Howell, MI", "url": "/marketplace/item/1290167646490252/"},
    {"title": "2015 Ford f-150", "price": "$17,495", "mileage": "140K miles", "location": "Wayne, MI", "url": "/marketplace/item/1420594729552972/"},
    {"title": "2023 Chevrolet colorado 4wd trail boss", "price": "$32,950", "mileage": "35K miles", "location": "Howell, MI", "url": "/marketplace/item/1220446983579169/"},
    {"title": "2015 Ford f150 supercrew cab XLT Pickup 4D 5 1/2 ft", "price": "$14,000", "mileage": "198K miles", "location": "Fowlerville, MI", "url": "/marketplace/item/875259588640731/"},
    {"title": "2017 Ford f-150 STX Pickup 4D 6 1/2 ft", "price": "$9,999", "mileage": "165K miles", "location": "Royal Oak, MI", "url": "/marketplace/item/1262130525735401/"},
    {"title": "2024 Ford ranger raptor", "price": "$53,627", "mileage": "5.4K miles", "location": "Toledo, OH", "url": "/marketplace/item/25799766942966855/"},
    {"title": "2017 Ford f-250 Platinum Ultimate", "price": "$26,999", "mileage": "278K miles", "location": "Newport, MI", "url": "/marketplace/item/759223096733625/"},
    {"title": "2016 Ford f-250 HD Long Bed", "price": "$17,000", "mileage": "116K miles", "location": "Canton, MI", "url": "/marketplace/item/913254324480920/"},
    {"title": "2017 GMC 1500 sle", "price": "$17,500", "mileage": "101K miles", "location": "Allen Park, MI", "url": "/marketplace/item/1211410757773408/"},
    {"title": "2016 Ford f-250", "price": "$11,000", "mileage": "128K miles", "location": "Trenton, MI", "url": "/marketplace/item/690979853983116/"},
    {"title": "2017 Ford f-150", "price": "$12,000", "mileage": "210K miles", "location": "Brighton, MI", "url": "/marketplace/item/1198582772340402/"},
    {"title": "2016 GMC sierra 1500 extended cab SLE Pickup 4D 6 1/2 ft", "price": "$12,891", "mileage": "193K miles", "location": "Fenton, MI", "url": "/marketplace/item/821097257615915/"},
    {"title": "2019 Ford f-150 Super cab 6.5 ft bed", "price": "$13,900", "mileage": "170K miles", "location": "Jackson, MI", "url": "/marketplace/item/1656673802162055/"},
    {"title": "2017 Ford f-150", "price": "$22,400", "mileage": "113K miles", "location": "Howell, MI", "url": "/marketplace/item/1400702605187392/"},
    {"title": "2014 Chevrolet silverado c1500", "price": "$3,600", "mileage": "250K miles", "location": "Clarkston, MI", "url": "/marketplace/item/900836512527686/"},
]

def main():
    start_time = datetime.utcnow()
    
    # Initialize database
    conn = init_db()
    
    # Process each listing
    seen_ids = []
    new_count = 0
    
    for data in listings_data:
        listing = parse_listing(data)
        if listing.get('id'):
            seen_ids.append(listing['id'])
            
            # Check if it's new
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM listings WHERE id = ?", (listing['id'],))
            if not cursor.fetchone():
                new_count += 1
            
            upsert_listing(conn, listing)
    
    # Mark unseen listings as inactive
    inactive_count = mark_inactive_listings(conn, seen_ids)
    
    # Record this scrape run
    duration = (datetime.utcnow() - start_time).total_seconds()
    stats = {
        'found': len(listings_data),
        'new': new_count,
        'inactive': inactive_count,
        'duration': duration,
        'status': 'success'
    }
    record_scrape_run(conn, stats)
    
    conn.close()
    
    # Print summary
    print(f"✅ Scrape complete!")
    print(f"Found: {stats['found']} trucks")
    print(f"New: {stats['new']}")
    print(f"Marked inactive: {stats['inactive']}")
    print(f"Duration: {stats['duration']:.2f}s")

if __name__ == '__main__':
    main()
