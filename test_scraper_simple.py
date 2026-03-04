#!/usr/bin/env python3
"""Quick test of scraper improvements."""

import logging
import json

# Setup logging  
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M"
)

from scraper import fetch_articles

print("\n" + "="*70)
print("Testing BBC News scraper...")
print("="*70 + "\n")

articles = fetch_articles('https://www.bbc.co.uk/news', 'Climate Change', max_articles=10)

print("\n" + "="*70)
print(f"RESULT: Found {len(articles)} articles")
print("="*70)

if articles:
    print("\nFirst 3 articles:")
    for i, art in enumerate(articles[:3], 1):
        print(f"\n{i}. {art['title']}")
        print(f"   URL: {art['url']}")
        print(f"   Level: {art['level']}")
        if art['content']:
            print(f"   Content preview: {art['content'][:100]}...")
else:
    print("\n❌ No articles found. Checking logs above for details.")
    print("   Common issues:")
    print("   - Network connectivity")
    print("   - RSS feed not accessible") 
    print("   - Homepage not scrapable")
    print("   - Rate limiting or blocking")
