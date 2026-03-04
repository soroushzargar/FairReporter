"""
analyzer.py
===========
LLM-based analysis of scraped articles and comparison of two news agencies'
coverage on a shared topic.
"""

import json
import logging
import re
from collections import Counter
from typing import Any, Dict, List

from llm_discovery import query_ollama, DEFAULT_MODEL, DEFAULT_OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment / stance analysis
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT = """\
You are a neutral media-analysis assistant.

Topic: {topic}

Article:
\"\"\"
{content}
\"\"\"

Analyze this article and respond with ONLY valid JSON in the following format (no extra text):
{{
  "sentiment": "<positive|negative|neutral>",
  "polarity": "<very_negative|negative|slightly_negative|neutral|slightly_positive|positive|very_positive>",
  "subjectivity": "<objective|mixed|opinionated>",
  "topic_relevance": <integer from 0 to 100 indicating how much the article is about the topic>,
  "framing": "<policy|economic|humanitarian|security|scientific|political|other>",
  "tone": "<alarmist|critical|balanced|supportive|neutral>",
  "stance": "<brief 1-sentence description of the article's narrative stance>",
  "key_points": ["<point 1>", "<point 2>", "<point 3>"],
  "score": <integer from -5 (very negative) to 5 (very positive)>
}}
"""


def _parse_json_response(raw: str) -> Dict[str, Any]:
    """Extract and parse the first JSON object found in *raw*."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Fallback: return a neutral placeholder
    return {
        "sentiment": "neutral",
        "polarity": "neutral",
        "subjectivity": "mixed",
        "topic_relevance": 50,
        "framing": "other",
        "tone": "neutral",
        "stance": "",
        "key_points": [],
        "score": 0,
    }


def _topic_keywords(topic: str) -> List[str]:
    """Build normalized topic keywords for relevance filtering."""
    words = re.findall(r"[a-zA-Z0-9]+", (topic or "").lower())
    if not words:
        return []
    keywords = {" ".join(words)}
    keywords.update(w for w in words if len(w) >= 4)
    return sorted(keywords)


def _topic_match_score(article: Dict, topic_keywords: List[str]) -> float:
    """Return [0..1] score indicating textual match against topic keywords."""
    if not topic_keywords:
        return 1.0
    haystack = " ".join([
        article.get("title") or "",
        article.get("content") or "",
    ]).lower()
    if not haystack.strip():
        return 0.0

    matched = sum(1 for kw in topic_keywords if kw in haystack)
    return matched / len(topic_keywords)


def filter_articles_by_topic(articles: List[Dict], topic: str, min_score: float = 0.3) -> List[Dict]:
    """
    Keep only articles with sufficient textual overlap to *topic*.

    If no article passes the threshold, returns the original list so the
    pipeline stays resilient on sparse feeds.
    """
    topic_keywords = _topic_keywords(topic)
    if not topic_keywords:
        return articles

    filtered = []
    for article in articles:
        score = _topic_match_score(article, topic_keywords)
        if score >= min_score:
            filtered.append(article)

    return filtered or articles


def analyze_article(
    article: Dict,
    topic: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> Dict:
    """
    Analyze a single article dict for sentiment and narrative stance using
    the Ollama LLM.

    The article dict must have at least a ``content`` key.  The analysis
    result is merged into a copy of the article dict and returned.

    Parameters
    ----------
    article : dict
        Article metadata including ``content``.
    topic : str
        The topic being researched.
    model : str
        Ollama model tag.
    base_url : str
        Ollama server base URL.

    Returns
    -------
    dict
        Article dict enriched with ``sentiment``, ``stance``,
        ``key_points``, and ``score``.
    """
    content = article.get("content") or article.get("title") or ""
    if not content:
        return {**article, **_parse_json_response("")}

    # Truncate very long content to keep prompts manageable
    content_snippet = content[:2000]
    prompt = _ANALYSIS_PROMPT.format(topic=topic, content=content_snippet)

    try:
        raw = query_ollama(prompt, model=model, base_url=base_url)
        analysis = _parse_json_response(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM analysis failed for %s: %s", article.get("url", "?"), exc)
        analysis = _parse_json_response("")

    return {**article, **analysis}


def analyze_articles(
    articles: List[Dict],
    agency_name: str,
    topic: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> List[Dict]:
    """
    Analyze all articles from *agency_name* and return enriched dicts.

    Parameters
    ----------
    articles : list of dict
        Raw article dicts from the scraper.
    agency_name : str
        Human-readable agency name (stored on each result for convenience).
    topic : str
        The topic being researched.
    model : str
        Ollama model tag.
    base_url : str
        Ollama server base URL.

    Returns
    -------
    list of dict
        Each article dict enriched with LLM analysis fields plus
        ``agency`` key.
    """
    scoped_articles = filter_articles_by_topic(articles, topic)
    if len(scoped_articles) != len(articles):
        logger.info(
            "[%s] Topic filter kept %d/%d article(s) for '%s'",
            agency_name,
            len(scoped_articles),
            len(articles),
            topic,
        )

    results = []
    total = len(scoped_articles)
    for idx, article in enumerate(scoped_articles, 1):
        logger.info("[%s] Analyzing article %d/%d: %s", agency_name, idx, total, article.get("url", ""))
        enriched = analyze_article(article, topic=topic, model=model, base_url=base_url)
        enriched["agency"] = agency_name
        results.append(enriched)
    return results


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _sentiment_distribution(articles: List[Dict]) -> Dict[str, int]:
    counts: Counter = Counter(a.get("sentiment", "neutral") for a in articles)
    return {"positive": counts.get("positive", 0), "negative": counts.get("negative", 0), "neutral": counts.get("neutral", 0)}


def _average_score(articles: List[Dict]) -> float:
    scores = [a.get("score", 0) for a in articles if isinstance(a.get("score"), (int, float))]
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def _top_keywords(articles: List[Dict], n: int = 30) -> List[Dict]:
    """
    Return the *n* most-common significant words across all article titles
    and content in *articles*.
    """
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "its", "it", "this", "that", "these",
        "those", "as", "not", "he", "she", "they", "we", "i", "you", "said",
        "says", "also", "after", "before", "about", "up", "out", "more",
        "than", "into", "s", "t",
    }
    word_re = re.compile(r"[a-zA-Z]{3,}")
    counter: Counter = Counter()
    for art in articles:
        text = ((art.get("title") or "") + " " + (art.get("content") or "")).lower()
        for word in word_re.findall(text):
            if word not in stopwords:
                counter[word] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(n)]


def _articles_by_date(articles: List[Dict]) -> Dict[str, int]:
    """Group articles by date string (YYYY-MM-DD prefix) for timeline data."""
    counts: Counter = Counter()
    for art in articles:
        date = art.get("date", "")
        if date:
            day = date[:10]  # take YYYY-MM-DD portion
            counts[day] += 1
    return dict(sorted(counts.items()))


def _distribution(articles: List[Dict], field: str, allowed: List[str]) -> Dict[str, int]:
    counts: Counter = Counter(a.get(field, "") for a in articles)
    return {k: counts.get(k, 0) for k in allowed}


def _average_topic_relevance(articles: List[Dict]) -> float:
    scores = [a.get("topic_relevance") for a in articles if isinstance(a.get("topic_relevance"), (int, float))]
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def _overlap_keywords(kw1: List[Dict], kw2: List[Dict]) -> List[str]:
    """Return words that appear in both keyword lists."""
    set1 = {k["word"] for k in kw1}
    set2 = {k["word"] for k in kw2}
    return sorted(set1 & set2)


def compare_agencies(
    agency1_results: List[Dict],
    agency2_results: List[Dict],
    agency1_name: str,
    agency2_name: str,
    topic: str,
) -> Dict:
    """
    Compute a structured comparison between two agencies' article analyses.

    Returns
    -------
    dict with keys:
    - ``topic``
    - ``agency1`` / ``agency2``  (name, article_count, sentiment_distribution,
      average_score, top_keywords, articles_by_date)
    - ``overlap_keywords``  (words appearing in both agencies' top keywords)
    - ``stance_summary``    (plain-English description generated from scores)
    """
    kw1 = _top_keywords(agency1_results)
    kw2 = _top_keywords(agency2_results)

    avg1 = _average_score(agency1_results)
    avg2 = _average_score(agency2_results)

    def stance_label(score: float) -> str:
        if score > 1.5:
            return "broadly positive"
        if score < -1.5:
            return "broadly negative"
        return "broadly neutral"

    stance_summary = (
        f"On the topic of '{topic}', {agency1_name} tends to cover it "
        f"{stance_label(avg1)} (avg score {avg1:+.1f}), while {agency2_name} "
        f"tends to cover it {stance_label(avg2)} (avg score {avg2:+.1f})."
    )

    return {
        "topic": topic,
        "agency1": {
            "name": agency1_name,
            "article_count": len(agency1_results),
            "sentiment_distribution": _sentiment_distribution(agency1_results),
            "polarity_distribution": _distribution(
                agency1_results,
                "polarity",
                [
                    "very_negative",
                    "negative",
                    "slightly_negative",
                    "neutral",
                    "slightly_positive",
                    "positive",
                    "very_positive",
                ],
            ),
            "subjectivity_distribution": _distribution(agency1_results, "subjectivity", ["objective", "mixed", "opinionated"]),
            "framing_distribution": _distribution(
                agency1_results,
                "framing",
                ["policy", "economic", "humanitarian", "security", "scientific", "political", "other"],
            ),
            "tone_distribution": _distribution(
                agency1_results,
                "tone",
                ["alarmist", "critical", "balanced", "supportive", "neutral"],
            ),
            "average_score": avg1,
            "average_topic_relevance": _average_topic_relevance(agency1_results),
            "top_keywords": kw1,
            "articles_by_date": _articles_by_date(agency1_results),
            "articles": agency1_results,
        },
        "agency2": {
            "name": agency2_name,
            "article_count": len(agency2_results),
            "sentiment_distribution": _sentiment_distribution(agency2_results),
            "polarity_distribution": _distribution(
                agency2_results,
                "polarity",
                [
                    "very_negative",
                    "negative",
                    "slightly_negative",
                    "neutral",
                    "slightly_positive",
                    "positive",
                    "very_positive",
                ],
            ),
            "subjectivity_distribution": _distribution(agency2_results, "subjectivity", ["objective", "mixed", "opinionated"]),
            "framing_distribution": _distribution(
                agency2_results,
                "framing",
                ["policy", "economic", "humanitarian", "security", "scientific", "political", "other"],
            ),
            "tone_distribution": _distribution(
                agency2_results,
                "tone",
                ["alarmist", "critical", "balanced", "supportive", "neutral"],
            ),
            "average_score": avg2,
            "average_topic_relevance": _average_topic_relevance(agency2_results),
            "top_keywords": kw2,
            "articles_by_date": _articles_by_date(agency2_results),
            "articles": agency2_results,
        },
        "overlap_keywords": _overlap_keywords(kw1, kw2),
        "stance_summary": stance_summary,
    }
