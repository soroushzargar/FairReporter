#!/usr/bin/env python3
"""Debug script to test the scraper."""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from scraper import fetch_articles

print("\nTesting BBC News with 'Climate Change' topic...")
articles = fetch_articles('https://www.bbc.co.uk/news', 'Climate Change', max_articles=10)
print(f'\n✓ Found {len(articles)} articles\n')

if articles:
    for i, art in enumerate(articles[:5], 1):
        print(f'{i}. {art["title"][:70]}')
        print(f'   Level: {art["level"]}, URL: {art["url"][:60]}...')
        print()
else:
    print("No articles found. Checking possible issues...")
    print("- RSS feed might not be accessible") 
    print("- Topic keywords might not match any articles")
    print("- Network issues or rate limiting")

