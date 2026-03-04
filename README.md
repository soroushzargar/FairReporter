# FairReporter
Comparing News Agencies on Their Bias Towards Some Specific Topic

FairReporter fetches recent articles from two news agencies, analyses each
article's sentiment and narrative stance using a local **Ollama** LLM, and
produces interactive **D3.js** visualizations so you can see how differently
(or similarly) the agencies cover a topic.

---

## Project structure

| File | Purpose |
|------|---------|
| `llm_discovery.py` | Query Ollama to discover each agency's website URL and RSS feed |
| `scraper.py` | Adaptively scrape up to 100 articles (full text → abstract → title) |
| `analyzer.py` | LLM-based sentiment / stance analysis and agency comparison |
| `visualizer.py` | Generate D3.js timeline, word-cloud, and dashboard HTML files || `main.py` | CLI entry point tying everything together |
| `requirements.txt` | Python dependencies |

---

## Requirements

- Python 3.9+
- A running [Ollama](https://ollama.ai) server (default: `http://localhost:11434`)
- An Ollama model pulled locally (e.g. `ollama pull llama3`)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
python main.py --agency1 "BBC News" --agency2 "Al Jazeera" --topic "Climate Change"
```

### All options

| Flag | Default | Description |
|------|---------|-------------|
| `--agency1` | *(required)* | Name of the first news agency |
| `--agency2` | *(required)* | Name of the second news agency |
| `--topic` | *(required)* | Topic to compare (e.g. `"Climate Change"`) |
| `--model` | `llama3` | Ollama model tag |
| `--ollama-url` | `http://localhost:11434` | Ollama server base URL |
| `--output` | `output` | Directory for output files |
| `--max` | `100` | Maximum articles per agency |
| `--url1` | | Override homepage URL for agency 1 (skip LLM discovery) |
| `--url2` | | Override homepage URL for agency 2 (skip LLM discovery) |

### Example with URL overrides

```bash
python main.py \
  --agency1 "BBC News" --url1 "https://www.bbc.com/news" \
  --agency2 "Al Jazeera" --url2 "https://www.aljazeera.com" \
  --topic "Climate Change" \
  --model mistral \
  --max 50
```

---

## Output

All files are written to the `output/` directory (created automatically):

| File | Contents |
|------|---------|
| `stats.json` | Raw comparison statistics |
| `cache/*.json` | Cached fetched articles keyed by agency/topic/max |
| `timeline.html` | D3.js dual-agency article-frequency timeline |
| `wordcloud.html` | D3.js side-by-side word clouds |
| `dashboard.html` | Combined interactive summary dashboard |

Open `output/dashboard.html` in any modern browser to explore the results.

### Fetch cache

Fetched article lists are cached under `output/cache/`. If you run the same
agency/topic/max combination again, FairReporter loads the cached articles
instead of scraping again.

---

## How it works

1. **URL discovery** — The LLM is asked for the official website of each
   agency.  RSS/Atom feed discovery follows.
2. **Scraping** — Up to `--max` articles are fetched.  For each article the
   scraper tries (in order): full body text, abstract (title + first
   paragraphs), title only.
3. **Analysis** — Each article is sent to the LLM which returns a JSON
   object with `sentiment`, `stance`, `key_points`, and a numeric `score`
   (−5 … +5).
4. **Comparison** — Aggregated statistics (sentiment distribution, average
   score, top keywords, overlap) are computed.
5. **Visualization** — D3.js HTML files are written to `output/`.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Default model |
