"""
llm_discovery.py
================
Query an Ollama LLM server to discover news agency website URLs and RSS feeds
given only the agency name.
"""

import os
import re
import json
import logging
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
REQUEST_TIMEOUT = 120  # seconds


# ---------------------------------------------------------------------------
# Low-level Ollama API call
# ---------------------------------------------------------------------------

def query_ollama(prompt: str, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_OLLAMA_BASE_URL) -> str:
    """
    Send *prompt* to the Ollama /api/generate endpoint and return the
    plain-text response string.

    Parameters
    ----------
    prompt : str
        The user prompt to send.
    model : str
        Ollama model tag (e.g. ``"llama3"``, ``"mistral"``).
    base_url : str
        Base URL of the Ollama server (default ``http://localhost:11434``).

    Returns
    -------
    str
        The model's response text.

    Raises
    ------
    requests.RequestException
        On network or HTTP errors.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


# ---------------------------------------------------------------------------
# URL discovery helpers
# ---------------------------------------------------------------------------

def _extract_url(text: str) -> str:
    """
    Extract the first URL-like string from *text*.

    Returns an empty string if no URL is found.
    """
    pattern = r"https?://[^\s\"'<>)}\]]*"
    match = re.search(pattern, text)
    return match.group(0).rstrip(".,;") if match else ""


def discover_agency_url(
    agency_name: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> str:
    """
    Ask the LLM to return the official homepage URL for *agency_name*.

    Parameters
    ----------
    agency_name : str
        Human-readable name such as ``"BBC News"`` or ``"Al Jazeera"``.
    model : str
        Ollama model to use.
    base_url : str
        Ollama server base URL.

    Returns
    -------
    str
        The discovered URL, or an empty string if the LLM did not provide one.
    """
    prompt = (
        f"What is the official website URL for the news agency called '{agency_name}'?\n"
        "Respond with ONLY the URL (starting with https:// or http://), nothing else."
    )
    logger.info("Asking LLM for URL of '%s'", agency_name)
    try:
        raw = query_ollama(prompt, model=model, base_url=base_url)
        url = _extract_url(raw)
        logger.info("Discovered URL for '%s': %s", agency_name, url or "(none)")
        return url
    except requests.RequestException as exc:
        logger.error("LLM request failed while discovering URL: %s", exc)
        return ""


def discover_rss_url(
    agency_name: str,
    homepage_url: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> str:
    """
    Ask the LLM to suggest the most likely RSS/Atom feed URL for *agency_name*
    given its *homepage_url*.

    Returns
    -------
    str
        Suggested RSS URL, or an empty string.
    """
    prompt = (
        f"The news agency '{agency_name}' has its homepage at {homepage_url}.\n"
        "What is the most likely URL for its main RSS or Atom news feed?\n"
        "Respond with ONLY the URL, nothing else."
    )
    logger.info("Asking LLM for RSS feed URL of '%s'", agency_name)
    try:
        raw = query_ollama(prompt, model=model, base_url=base_url)
        url = _extract_url(raw)
        logger.info("Discovered RSS for '%s': %s", agency_name, url or "(none)")
        return url
    except requests.RequestException as exc:
        logger.error("LLM request failed while discovering RSS: %s", exc)
        return ""
