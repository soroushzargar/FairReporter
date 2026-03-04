"""
scraper.py
==========
Adaptive article scraper for news agency websites.

Fetch strategy (applied per article, in order):
  1. Full article text via ``<article>`` / ``<p>`` tags
  2. Abstract — title + first two sentences of body
  3. Title only

Up to *max_articles* recent articles are returned per agency.
RSS/Atom feeds are tried first; if unavailable, the homepage is parsed for
links.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 20  # seconds per HTTP request
REQUEST_DELAY = 0.5   # polite delay between requests (seconds)
MAX_ARTICLES = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FairReporter/1.0; "
        "+https://github.com/soroushzargar/FairReporter)"
    )
}

# Common RSS/Atom path suffixes to probe
RSS_SUFFIXES = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/feed.xml",
    "/feeds/posts/default",
    "/news.rss",
    "/rss2",
    "/atom.xml",
    "/index.rss",
    "/en/rss.xml",
    "/feed/rss2",
]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    """GET *url* and return the Response, or None on any error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        logger.debug("GET %s failed: %s", url, exc)
        return None


def _base_url(url: str) -> str:
    """Return scheme + netloc of *url* (e.g. ``https://example.com``)."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def _extract_full_text(soup: BeautifulSoup) -> str:
    """
    Try to extract the full article body text.

    Looks for ``<article>``, ``<main>``, or a div with common content
    class names.  Returns an empty string if nothing useful is found.
    """
    candidates = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"article[-_]?body|post[-_]?content|entry[-_]?content", re.I))
        or soup.find("div", id=re.compile(r"article[-_]?body|post[-_]?content|main[-_]?content", re.I))
    )
    if candidates:
        paragraphs = candidates.find_all("p")
        text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
        if len(text) > 50:
            return text
    return ""


def _extract_abstract(soup: BeautifulSoup) -> str:
    """
    Return title + first two non-empty paragraphs as an abstract.
    """
    title = soup.find("h1")
    title_text = title.get_text(" ", strip=True) if title else ""

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
    snippet = " ".join(paragraphs[:2])
    return f"{title_text}. {snippet}".strip() if snippet else title_text


def _extract_title(soup: BeautifulSoup) -> str:
    """Return the page/article title."""
    tag = soup.find("h1") or soup.find("title")
    return tag.get_text(" ", strip=True) if tag else ""


def fetch_article_content(url: str) -> Dict:
    """
    Adaptively fetch content from a single article URL.

    Returns a dict with keys:
    - ``url``   : article URL
    - ``title`` : article title
    - ``content``: best available text (full / abstract / title)
    - ``level`` : ``"full"``, ``"abstract"``, or ``"title"``
    - ``date``  : publication date string (may be empty)
    """
    result = {"url": url, "title": "", "content": "", "level": "title", "date": ""}
    time.sleep(REQUEST_DELAY)
    resp = _get(url)
    if resp is None:
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # Attempt 1: full text
    full = _extract_full_text(soup)
    if full:
        result["level"] = "full"
        result["content"] = full
    else:
        # Attempt 2: abstract
        abstract = _extract_abstract(soup)
        if abstract:
            result["level"] = "abstract"
            result["content"] = abstract
        else:
            # Fallback: title only
            result["content"] = _extract_title(soup)
            result["level"] = "title"

    result["title"] = _extract_title(soup)

    # Best-effort date extraction
    date_tag = (
        soup.find("time")
        or soup.find("meta", attrs={"property": "article:published_time"})
        or soup.find("meta", attrs={"name": "pubdate"})
    )
    if date_tag:
        result["date"] = date_tag.get("datetime") or date_tag.get("content") or date_tag.get_text(strip=True)

    return result


# ---------------------------------------------------------------------------
# RSS scraping
# ---------------------------------------------------------------------------

def _find_rss_url(base: str, homepage_url: str) -> Optional[str]:
    """
    Try common RSS suffixes and auto-discovered feed links for *base*.

    Parameters
    ----------
    base : str
        Base URL (scheme + netloc).
    homepage_url : str
        Full homepage URL; checked for ``<link rel="alternate">`` tags.

    Returns
    -------
    str or None
        First working RSS URL found, or None.
    """
    # Check homepage HTML for <link rel="alternate" type="application/rss+xml">
    resp = _get(homepage_url)
    if resp:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all("link", rel="alternate"):
            t = tag.get("type", "")
            if "rss" in t or "atom" in t:
                href = tag.get("href", "")
                if href:
                    return urljoin(base, href)

    # Probe known suffixes
    for suffix in RSS_SUFFIXES:
        candidate = base + suffix
        resp = _get(candidate)
        if resp and ("xml" in resp.headers.get("Content-Type", "") or resp.text.strip().startswith("<")):
            parsed = feedparser.parse(resp.text)
            if parsed.entries:
                return candidate

    return None


def _articles_from_feed(feed_url: str, topic: str, max_articles: int) -> List[Dict]:
    """
    Parse an RSS/Atom feed and return article stubs filtered by *topic*.

    Each stub contains ``url``, ``title``, ``date``, ``content`` (summary
    from feed), and ``level`` = ``"abstract"``.
    """
    resp = _get(feed_url)
    if resp is None:
        return []

    parsed = feedparser.parse(resp.text)
    articles = []
    topic_lower = topic.lower()
    
    # Create a list of topic keywords for more flexible matching
    topic_keywords = []
    if topic_lower:
        # Add the full topic
        topic_keywords.append(topic_lower)
        # Add individual words from the topic (for multi-word topics like "Climate Change")
        topic_keywords.extend([word.strip() for word in topic_lower.split() if len(word.strip()) > 3])

    for entry in parsed.entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        link = entry.get("link", "")
        date = entry.get("published", "") or entry.get("updated", "")

        # Flexible topic relevance filter - match any keyword
        combined = (title + " " + summary).lower()
        if topic_keywords:
            # If at least one keyword matches, include the article
            if not any(keyword in combined for keyword in topic_keywords):
                continue

        articles.append({
            "url": link,
            "title": title,
            "content": summary or title,
            "level": "abstract" if summary else "title",
            "date": date,
        })

        if len(articles) >= max_articles:
            break

    return articles


def _articles_from_feed_no_filter(feed_url: str, max_articles: int) -> List[Dict]:
    """
    Parse an RSS/Atom feed and return recent article stubs WITHOUT any topic filtering.
    Used as a fallback when topic-based filtering returns no results.
    """
    resp = _get(feed_url)
    if resp is None:
        return []

    parsed = feedparser.parse(resp.text)
    articles = []

    for entry in parsed.entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        link = entry.get("link", "")
        date = entry.get("published", "") or entry.get("updated", "")

        articles.append({
            "url": link,
            "title": title,
            "content": summary or title,
            "level": "abstract" if summary else "title",
            "date": date,
        })

        if len(articles) >= max_articles:
            break

    return articles




def _articles_from_homepage(homepage_url: str, topic: str, max_articles: int) -> List[Dict]:
    """
    Scrape the homepage for article links and fetch each one adaptively.
    """
    resp = _get(homepage_url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    base = _base_url(homepage_url)
    topic_lower = topic.lower()
    
    # Create a list of topic keywords for more flexible matching
    topic_keywords = []
    if topic_lower:
        topic_keywords.append(topic_lower)
        topic_keywords.extend([word.strip() for word in topic_lower.split() if len(word.strip()) > 3])

    seen: Set[str] = set()
    links: List[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        full_url = urljoin(base, href)
        if full_url in seen:
            continue
        # Heuristic: article URLs tend to have path depth >= 2 and a slug
        path = urlparse(full_url).path
        if len(path.split("/")) < 3:
            continue
        # Flexible topic filter on anchor text - match any keyword
        anchor_text = a_tag.get_text(" ", strip=True).lower()
        if topic_keywords:
            if not any(keyword in anchor_text for keyword in topic_keywords):
                continue
        seen.add(full_url)
        links.append(full_url)
        if len(links) >= max_articles:
            break

    articles = []
    for url in links[:max_articles]:
        article = fetch_article_content(url)
        if article["content"]:
            articles.append(article)
    return articles


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch_articles(
    agency_url: str,
    topic: str,
    rss_url: Optional[str] = None,
    max_articles: int = MAX_ARTICLES,
) -> List[Dict]:
    """
    Fetch up to *max_articles* recent articles from *agency_url* related to
    *topic*, using the following strategy:

    1. If *rss_url* is provided, use it.
    2. Otherwise, auto-discover the RSS feed from the homepage.
    3. If no RSS feed is found, fall back to scraping the homepage for links
       and fetching each article adaptively.

    Parameters
    ----------
    agency_url : str
        Homepage (or any entry-point) URL for the news agency.
    topic : str
        Topic keyword to filter articles (case-insensitive substring match).
    rss_url : str, optional
        Pre-discovered RSS/Atom feed URL.
    max_articles : int
        Maximum number of articles to return (default 100).

    Returns
    -------
    list of dict
        Each dict has: ``url``, ``title``, ``content``, ``level``, ``date``.
    """
    base = _base_url(agency_url)

    # Step 1 / 2: RSS
    if not rss_url:
        logger.info("Auto-discovering RSS feed for %s", agency_url)
        rss_url = _find_rss_url(base, agency_url)

    if rss_url:
        logger.info("Using RSS feed: %s", rss_url)
        # Try with topic filter first
        articles = _articles_from_feed(rss_url, topic, max_articles)
        logger.info("Got %d articles from RSS (after topic filter)", len(articles))
        
        # If topic filter returned nothing, try without filter  
        if not articles and topic:
            logger.info("Topic filter removed all articles; retrying RSS without topic filter")
            articles = _articles_from_feed_no_filter(rss_url, max_articles)
            logger.info("Got %d articles from RSS (without topic filter)", len(articles))
        
        if articles:
            # Optionally enrich with full-text fetch for articles that only
            # have summary-level content from the feed
            enriched = []
            for art in articles:
                if art["level"] == "abstract" and art["url"]:
                    full = fetch_article_content(art["url"])
                    if full["level"] == "full":
                        art.update(full)
                enriched.append(art)
            return enriched[:max_articles]
        else:
            logger.warning("RSS feed exists but has no articles")

    # Step 3: homepage fallback  
    logger.info("Trying homepage fallback: %s", agency_url)
    articles = _articles_from_homepage(agency_url, topic, max_articles)
    logger.info("Got %d articles from homepage (with topic filter)", len(articles))
    
    # If homepage with topic filter returns nothing, try without filter
    if not articles and topic:
        logger.warning("Homepage topic filter returned no results; scraping without topic filter")
        articles = _articles_from_homepage(agency_url, "", max_articles)
        logger.info("Got %d articles from homepage (without topic filter)", len(articles))
    
    return articles
