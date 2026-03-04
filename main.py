"""
main.py
=======
FairReporter — CLI entry point.

Usage
-----
  python main.py --agency1 "BBC News" --agency2 "Al Jazeera" --topic "Climate Change"

Optional flags:
  --model      Ollama model tag       (default: llama3)
  --ollama-url Ollama server base URL (default: http://localhost:11434)
  --output     Output directory       (default: output)
  --max        Maximum articles per agency (default: 100)
"""

import argparse
import hashlib
import json
import logging
import os
import sys

from llm_discovery import discover_agency_url, discover_rss_url, DEFAULT_MODEL, DEFAULT_OLLAMA_BASE_URL
from scraper import fetch_articles
from analyzer import analyze_articles, compare_agencies
from visualizer import save_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CACHE_DIR = "cache"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two news agencies' coverage on a topic using an Ollama LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--agency1", required=True, help="Name of the first news agency")
    parser.add_argument("--agency2", required=True, help="Name of the second news agency")
    parser.add_argument("--topic", required=True, help="Topic to compare (e.g. 'Climate Change')")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model tag")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_BASE_URL, dest="ollama_url",
                        help="Ollama server base URL")
    parser.add_argument("--output", default="output", help="Output directory for results")
    parser.add_argument("--max", type=int, default=100, dest="max_articles",
                        help="Maximum articles to fetch per agency (default: 100)")
    parser.add_argument("--url1", default="", help="Override URL for agency 1 (skip LLM discovery)")
    parser.add_argument("--url2", default="", help="Override URL for agency 2 (skip LLM discovery)")
    return parser


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def _cache_file_path(
    agency_name: str,
    agency_url: str,
    topic: str,
    max_articles: int,
    output_dir: str,
) -> str:
    """Return deterministic cache path for one fetch request."""
    marker = {
        "agency_name": agency_name.strip().lower(),
        "agency_url": agency_url.strip().lower(),
        "topic": topic.strip().lower(),
        "max_articles": int(max_articles),
    }
    raw = json.dumps(marker, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    safe_agency = "".join(c if c.isalnum() else "_" for c in agency_name.strip().lower()).strip("_")
    if not safe_agency:
        safe_agency = "agency"
    file_name = f"{safe_agency}_{digest}.json"
    return os.path.join(output_dir, CACHE_DIR, file_name)


def _load_fetch_cache(cache_path: str):
    """Load cached articles if available and valid."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        articles = payload.get("articles")
        if isinstance(articles, list):
            logger.info("Loaded %d cached article(s) from %s", len(articles), cache_path)
            return articles
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read cache file %s: %s", cache_path, exc)
    return None


def _save_fetch_cache(cache_path: str, marker: dict, articles) -> None:
    """Persist fetched articles to cache."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    payload = {
        "marker": marker,
        "count": len(articles),
        "articles": articles,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d article(s) to cache: %s", len(articles), cache_path)

def _discover_url(agency_name: str, override: str, model: str, ollama_url: str) -> str:
    """Return a URL for *agency_name*, using *override* if provided."""
    if override:
        logger.info("Using provided URL for '%s': %s", agency_name, override)
        return override
    url = discover_agency_url(agency_name, model=model, base_url=ollama_url)
    if not url:
        logger.error(
            "Could not discover a URL for '%s'. "
            "Provide one with --url1 / --url2 or check your Ollama server.",
            agency_name,
        )
        sys.exit(1)
    return url


def _fetch(
    agency_name: str,
    agency_url: str,
    topic: str,
    model: str,
    ollama_url: str,
    max_articles: int,
    output_dir: str,
):
    """Discover RSS feed and scrape articles for one agency."""
    logger.info("=== %s (%s) ===", agency_name, agency_url)

    marker = {
        "agency_name": agency_name,
        "agency_url": agency_url,
        "topic": topic,
        "max_articles": max_articles,
    }
    cache_path = _cache_file_path(agency_name, agency_url, topic, max_articles, output_dir)
    cached_articles = _load_fetch_cache(cache_path)
    if cached_articles is not None:
        return cached_articles

    rss_url = discover_rss_url(agency_name, agency_url, model=model, base_url=ollama_url)
    articles = fetch_articles(agency_url, topic, rss_url=rss_url, max_articles=max_articles)
    _save_fetch_cache(cache_path, marker, articles)
    logger.info("Fetched %d article(s) for '%s'", len(articles), agency_name)
    return articles


def _analyze(agency_name: str, articles, topic: str, model: str, ollama_url: str):
    """Run LLM analysis on all articles for one agency."""
    logger.info("Analyzing %d article(s) for '%s' …", len(articles), agency_name)
    return analyze_articles(articles, agency_name, topic, model=model, base_url=ollama_url)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  FairReporter")
    print(f"  Topic   : {args.topic}")
    print(f"  Agency 1: {args.agency1}")
    print(f"  Agency 2: {args.agency2}")
    print(f"  Model   : {args.model} @ {args.ollama_url}")
    print(f"{'='*60}\n")

    # Step 1: URL discovery
    print("🔍  Step 1: Discovering agency URLs …")
    url1 = _discover_url(args.agency1, args.url1, args.model, args.ollama_url)
    url2 = _discover_url(args.agency2, args.url2, args.model, args.ollama_url)
    print(f"   {args.agency1}: {url1}")
    print(f"   {args.agency2}: {url2}\n")

    # Step 2: Scraping
    print("📥  Step 2: Scraping articles …")
    articles1 = _fetch(args.agency1, url1, args.topic, args.model, args.ollama_url, args.max_articles, args.output)
    articles2 = _fetch(args.agency2, url2, args.topic, args.model, args.ollama_url, args.max_articles, args.output)
    print(f"   {args.agency1}: {len(articles1)} article(s)")
    print(f"   {args.agency2}: {len(articles2)} article(s)\n")

    if not articles1 and not articles2:
        logger.warning("No articles found for either agency. Check connectivity or try different URLs.")

    # Step 3: Analysis
    print("🤖  Step 3: Analyzing articles with LLM …")
    results1 = _analyze(args.agency1, articles1, args.topic, args.model, args.ollama_url)
    results2 = _analyze(args.agency2, articles2, args.topic, args.model, args.ollama_url)

    # Step 4: Comparison
    print("📊  Step 4: Comparing agencies …")
    comparison = compare_agencies(results1, results2, args.agency1, args.agency2, args.topic)
    print(f"\n   {comparison['stance_summary']}\n")

    # Step 5: Visualisation & save
    print("💾  Step 5: Saving results …")
    save_all(comparison, output_dir=args.output)

    print("\n✨  Done!  Open output/dashboard.html in your browser to explore the results.\n")


if __name__ == "__main__":
    main()
