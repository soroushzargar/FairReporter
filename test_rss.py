#!/usr/bin/env python3
"""Simple test to check RSS feed discovery."""

import requests
import feedparser

print("Testing RSS feed discovery and parsing...\n")

# Test BBC News RSS
print("1. Testing BBC News RSS feed")
bbc_rss_url = "https://feeds.bbci.co.uk/news/rss.xml"
print(f"   URL: {bbc_rss_url}")

try:
    response = requests.get(bbc_rss_url, timeout=10)
    print(f"   Status: {response.status_code}")
    
    feed = feedparser.parse(response.text)
    print(f"   Entries found: {len(feed.entries)}")
    
    if feed.entries:
        print(f"   First article: {feed.entries[0].get('title', 'N/A')[:60]}")
        # Check for climate-related keywords
        climate_count = 0
        for entry in feed.entries[:20]:
            title = entry.get('title', '').lower()
            summary = entry.get('summary', '').lower()
            if 'climate' in title or 'climate' in summary:
                climate_count += 1
        print(f"   Articles with 'climate' (first 20): {climate_count}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n2. Testing Al Jazeera RSS feed")
aj_rss_url = "https://www.aljazeera.com/xml/rss/all.xml"
print(f"   URL: {aj_rss_url}")

try:
    response = requests.get(aj_rss_url, timeout=10)
    print(f"   Status: {response.status_code}")
    
    feed = feedparser.parse(response.text)
    print(f"   Entries found: {len(feed.entries)}")
    
    if feed.entries:
        print(f"   First article: {feed.entries[0].get('title', 'N/A')[:60]}")
        climate_count = 0
        for entry in feed.entries[:20]:
            title = entry.get('title', '').lower()
            summary = entry.get('summary', '').lower()
            if 'climate' in title or 'climate' in summary:
                climate_count += 1
        print(f"   Articles with 'climate' (first 20): {climate_count}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\nDone!")
