#!/usr/bin/env python3
"""Test scraper with Al Jazeera."""

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

from scraper import fetch_articles

print("\nTesting Al Jazeera scraper...\n")
articles = fetch_articles('https://aljazeera.net', 'Climate Change', max_articles=10)

print(f"\n✓ Found {len(articles)} articles from Al Jazeera\n")

if articles:
    for i, art in enumerate(articles[:3], 1):
        print(f"{i}. {art['title'][:70]}")
