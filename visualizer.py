"""
visualizer.py
=============
Generate D3.js-powered interactive HTML visualizations from the comparison
data produced by analyzer.compare_agencies().

Outputs saved by save_all():
  output/timeline.html    — dual-agency article-frequency timeline
  output/wordcloud.html   — side-by-side word clouds
  output/dashboard.html   — combined summary dashboard
  output/stats.json       — raw comparison statistics (no article text)
"""

import json
import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLORS = {"agency1": "#1f77b4", "agency2": "#ff7f0e"}


def _safe_json(data) -> str:
    """Serialize *data* to a compact JSON string safe for embedding in HTML."""
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

_TIMELINE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FairReporter — Timeline: {topic}</title>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; background: #fafafa; margin: 0; padding: 20px; }}
    h1 {{ text-align: center; color: #333; }}
    .subtitle {{ text-align: center; color: #666; margin-bottom: 20px; }}
    .chart-container {{ max-width: 900px; margin: 0 auto; background: #fff;
                        border: 1px solid #ddd; border-radius: 8px; padding: 20px; }}
    .legend {{ display: flex; justify-content: center; gap: 30px; margin-top: 10px; }}
    .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 14px; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    .tooltip {{ position: absolute; background: rgba(0,0,0,0.7); color: #fff;
                padding: 6px 10px; border-radius: 4px; font-size: 12px;
                pointer-events: none; opacity: 0; }}
    .axis-label {{ font-size: 12px; fill: #555; }}
  </style>
</head>
<body>
  <h1>Article Frequency Timeline</h1>
  <p class="subtitle">Topic: <strong>{topic}</strong></p>
  <div class="chart-container">
    <svg id="chart"></svg>
    <div class="legend">
      <div class="legend-item">
        <div class="legend-dot" style="background:{color1}"></div>
        <span>{agency1}</span>
      </div>
      <div class="legend-item">
        <div class="legend-dot" style="background:{color2}"></div>
        <span>{agency2}</span>
      </div>
    </div>
  </div>
  <div class="tooltip" id="tooltip"></div>

  <script>
    const agency1Name = {agency1_json};
    const agency2Name = {agency2_json};
    const data1 = {data1_json};
    const data2 = {data2_json};
    const color1 = "{color1}";
    const color2 = "{color2}";

    // Merge dates
    const allDates = Array.from(new Set([...Object.keys(data1), ...Object.keys(data2)])).sort();
    const rows = allDates.map(d => ({{
      date: new Date(d),
      v1: data1[d] || 0,
      v2: data2[d] || 0,
    }}));

    const margin = {{top: 20, right: 30, bottom: 50, left: 50}};
    const width = 860 - margin.left - margin.right;
    const height = 360 - margin.top - margin.bottom;

    const svg = d3.select("#chart")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
      .append("g")
      .attr("transform", `translate(${{margin.left}},${{margin.top}})`);

    const x = d3.scaleTime().domain(d3.extent(rows, d => d.date)).range([0, width]);
    const maxY = d3.max(rows, d => Math.max(d.v1, d.v2)) || 1;
    const y = d3.scaleLinear().domain([0, maxY]).nice().range([height, 0]);

    svg.append("g").attr("transform", `translate(0,${{height}})`).call(d3.axisBottom(x));
    svg.append("g").call(d3.axisLeft(y).ticks(5));

    // X label
    svg.append("text").attr("class","axis-label")
      .attr("x", width / 2).attr("y", height + 40)
      .attr("text-anchor","middle").text("Date");
    // Y label
    svg.append("text").attr("class","axis-label")
      .attr("transform","rotate(-90)")
      .attr("x", -height / 2).attr("y", -40)
      .attr("text-anchor","middle").text("Article Count");

    const line1 = d3.line().x(d => x(d.date)).y(d => y(d.v1)).curve(d3.curveMonotoneX);
    const line2 = d3.line().x(d => x(d.date)).y(d => y(d.v2)).curve(d3.curveMonotoneX);

    if (rows.length > 0) {{
      svg.append("path").datum(rows).attr("fill","none")
        .attr("stroke", color1).attr("stroke-width", 2.5).attr("d", line1);
      svg.append("path").datum(rows).attr("fill","none")
        .attr("stroke", color2).attr("stroke-width", 2.5).attr("d", line2);
    }}

    const tooltip = d3.select("#tooltip");

    function addDots(colorVal, accessor) {{
      svg.selectAll(null).data(rows).enter().append("circle")
        .attr("cx", d => x(d.date)).attr("cy", d => y(accessor(d)))
        .attr("r", 4).attr("fill", colorVal).attr("opacity", 0.8)
        .on("mouseover", (event, d) => {{
          tooltip.style("opacity",1)
            .html(`${{d.date.toISOString().slice(0,10)}}: ${{accessor(d)}} article(s)`)
            .style("left", (event.pageX+10)+"px").style("top", (event.pageY-28)+"px");
        }})
        .on("mouseout", () => tooltip.style("opacity", 0));
    }}
    addDots(color1, d => d.v1);
    addDots(color2, d => d.v2);
  </script>
</body>
</html>
"""


def generate_timeline_html(comparison: Dict) -> str:
    """Return a complete HTML string for the timeline visualization."""
    a1 = comparison["agency1"]
    a2 = comparison["agency2"]
    return _TIMELINE_TEMPLATE.format(
        topic=comparison["topic"],
        agency1=a1["name"],
        agency2=a2["name"],
        agency1_json=_safe_json(a1["name"]),
        agency2_json=_safe_json(a2["name"]),
        data1_json=_safe_json(a1["articles_by_date"]),
        data2_json=_safe_json(a2["articles_by_date"]),
        color1=_COLORS["agency1"],
        color2=_COLORS["agency2"],
    )


# ---------------------------------------------------------------------------
# Word cloud
# ---------------------------------------------------------------------------

_WORDCLOUD_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FairReporter — Word Cloud: {topic}</title>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/d3-cloud@1.2.5/build/d3.layout.cloud.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; background: #fafafa; margin: 0; padding: 20px; }}
    h1 {{ text-align: center; color: #333; }}
    .subtitle {{ text-align: center; color: #666; margin-bottom: 20px; }}
    .clouds {{ display: flex; justify-content: center; gap: 40px; flex-wrap: wrap; }}
    .cloud-box {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  padding: 10px; text-align: center; }}
    .cloud-box h2 {{ margin: 0 0 8px; font-size: 16px; }}
  </style>
</head>
<body>
  <h1>Word Cloud</h1>
  <p class="subtitle">Topic: <strong>{topic}</strong></p>
  <div class="clouds">
    <div class="cloud-box">
      <h2 style="color:{color1}">{agency1}</h2>
      <svg id="cloud1"></svg>
    </div>
    <div class="cloud-box">
      <h2 style="color:{color2}">{agency2}</h2>
      <svg id="cloud2"></svg>
    </div>
  </div>

  <script>
    const words1 = {words1_json};
    const words2 = {words2_json};
    const color1 = "{color1}";
    const color2 = "{color2}";

    function drawCloud(svgId, words, baseColor) {{
      const W = 380, H = 300;
      const maxCount = d3.max(words, d => d.count) || 1;
      const fontSize = d3.scaleLinear().domain([1, maxCount]).range([10, 48]);
      const colorScale = d3.scaleSequential(d3.interpolateBlues).domain([1, maxCount]);

      d3.layout.cloud()
        .size([W, H])
        .words(words.map(d => ({{text: d.word, size: fontSize(d.count), count: d.count}})))
        .padding(4)
        .rotate(() => (Math.random() > 0.5 ? 0 : 90))
        .font("Arial")
        .fontSize(d => d.size)
        .on("end", drawn)
        .start();

      function drawn(placed) {{
        const svg = d3.select("#" + svgId)
          .attr("width", W).attr("height", H);
        svg.append("g")
          .attr("transform", `translate(${{W/2}},${{H/2}})`)
          .selectAll("text")
          .data(placed)
          .enter().append("text")
          .style("font-size", d => d.size + "px")
          .style("font-family", "Arial")
          .style("fill", d => colorScale(d.count))
          .attr("text-anchor", "middle")
          .attr("transform", d => `translate(${{d.x}},${{d.y}})rotate(${{d.rotate}})`)
          .text(d => d.text)
          .append("title").text(d => `${{d.text}}: ${{d.count}}`);
      }}
    }}

    drawCloud("cloud1", words1, color1);
    drawCloud("cloud2", words2, color2);
  </script>
</body>
</html>
"""


def generate_wordcloud_html(comparison: Dict) -> str:
    """Return a complete HTML string for the word-cloud visualization."""
    a1 = comparison["agency1"]
    a2 = comparison["agency2"]
    return _WORDCLOUD_TEMPLATE.format(
        topic=comparison["topic"],
        agency1=a1["name"],
        agency2=a2["name"],
        words1_json=_safe_json(a1["top_keywords"]),
        words2_json=_safe_json(a2["top_keywords"]),
        color1=_COLORS["agency1"],
        color2=_COLORS["agency2"],
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FairReporter — Dashboard: {topic}</title>
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }}
    h1 {{ text-align: center; color: #222; margin-bottom: 4px; }}
    .subtitle {{ text-align: center; color: #555; margin-bottom: 24px; font-size: 15px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1100px; margin: 0 auto; }}
    .card {{ background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 20px; }}
    .card h2 {{ margin: 0 0 12px; font-size: 16px; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
    .stat {{ font-size: 28px; font-weight: bold; }}
    .bar-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 13px; }}
    .bar {{ height: 18px; border-radius: 3px; transition: width 0.4s; }}
    .stance-box {{ background: #f9f9f9; border-radius: 6px; padding: 12px; font-size: 14px;
                   line-height: 1.6; grid-column: 1 / -1; }}
    .overlap-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .tag {{ background: #e8f0fe; color: #1a73e8; padding: 3px 9px; border-radius: 12px; font-size: 12px; }}
    .iframe-row {{ grid-column: 1 / -1; }}
    iframe {{ width: 100%; height: 400px; border: none; border-radius: 8px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    td, th {{ padding: 6px 10px; border-bottom: 1px solid #eee; text-align: left; }}
    th {{ background: #f5f5f5; }}
    a {{ color: #1a73e8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>FairReporter Dashboard</h1>
  <p class="subtitle">Coverage comparison on <strong>{topic}</strong></p>

  <div class="grid">

    <!-- Article counts -->
    <div class="card">
      <h2>📰 Articles Found</h2>
      <div style="display:flex;gap:30px">
        <div>
          <div style="color:{color1};font-size:13px">{agency1}</div>
          <div class="stat" style="color:{color1}" id="cnt1"></div>
        </div>
        <div>
          <div style="color:{color2};font-size:13px">{agency2}</div>
          <div class="stat" style="color:{color2}" id="cnt2"></div>
        </div>
      </div>
    </div>

    <!-- Average score -->
    <div class="card">
      <h2>📊 Average Sentiment Score</h2>
      <svg id="score-bars" width="280" height="80"></svg>
    </div>

    <!-- Sentiment distribution -->
    <div class="card">
      <h2>😊 Sentiment Distribution — {agency1}</h2>
      <svg id="sent1" width="260" height="120"></svg>
    </div>
    <div class="card">
      <h2>😊 Sentiment Distribution — {agency2}</h2>
      <svg id="sent2" width="260" height="120"></svg>
    </div>

    <!-- Stance summary -->
    <div class="stance-box card">
      <h2>🔍 Stance Summary</h2>
      <p id="stance-text"></p>
    </div>

    <!-- Overlap keywords -->
    <div class="card" style="grid-column: 1 / -1">
      <h2>🔗 Overlapping Keywords</h2>
      <div class="overlap-tags" id="overlap-tags"></div>
    </div>

    <!-- Top articles table -->
    <div class="card">
      <h2>📄 Recent Articles — {agency1}</h2>
      <table><thead><tr><th>Title</th><th>Sentiment</th><th>Score</th></tr></thead>
      <tbody id="table1"></tbody></table>
    </div>
    <div class="card">
      <h2>📄 Recent Articles — {agency2}</h2>
      <table><thead><tr><th>Title</th><th>Sentiment</th><th>Score</th></tr></thead>
      <tbody id="table2"></tbody></table>
    </div>

  </div>

  <script>
    const comparison = {comparison_json};
    const a1 = comparison.agency1;
    const a2 = comparison.agency2;
    const color1 = "{color1}";
    const color2 = "{color2}";

    // Counts
    document.getElementById("cnt1").textContent = a1.article_count;
    document.getElementById("cnt2").textContent = a2.article_count;

    // Stance
    document.getElementById("stance-text").textContent = comparison.stance_summary;

    // Overlap keywords
    const tagsDiv = document.getElementById("overlap-tags");
    (comparison.overlap_keywords || []).forEach(w => {{
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = w;
      tagsDiv.appendChild(span);
    }});

    // Score bars
    function drawScoreBars() {{
      const svg = d3.select("#score-bars");
      const barH = 22, gap = 12, pad = 10;
      const scaleW = 260;
      const x = d3.scaleLinear().domain([-5, 5]).range([0, scaleW]);

      [[a1.name, a1.average_score, color1], [a2.name, a2.average_score, color2]].forEach(([name, score, col], i) => {{
        const g = svg.append("g").attr("transform", `translate(${{pad}},${{i * (barH + gap)}})`);
        g.append("text").attr("y", barH - 6).style("font-size","12px").text(`${{name}}: ${{score >= 0 ? "+" : ""}}${{score}}`);
        g.append("rect").attr("x", x(0)).attr("y", 0)
          .attr("width", Math.abs(x(score) - x(0))).attr("height", barH - 10)
          .attr("transform", score < 0 ? `translate(${{x(score) - x(0)}},0)` : "")
          .attr("fill", col).attr("rx", 3);
        // zero line
        g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", 0).attr("y2", barH - 8)
          .attr("stroke","#aaa").attr("stroke-width",1);
      }});
    }}
    drawScoreBars();

    // Sentiment pie
    function drawSentiment(svgId, dist, color) {{
      const data = [
        {{label:"positive", value: dist.positive, color:"#4caf50"}},
        {{label:"neutral",  value: dist.neutral,  color:"#9e9e9e"}},
        {{label:"negative", value: dist.negative, color:"#f44336"}},
      ].filter(d => d.value > 0);
      if (data.length === 0) return;
      const W = 120, H = 120, r = 50;
      const svg = d3.select("#" + svgId).attr("width", 260).attr("height", 120);
      const pie = d3.pie().value(d => d.value)(data);
      const arc = d3.arc().innerRadius(20).outerRadius(r);
      const g = svg.append("g").attr("transform", `translate(${{r+10}},${{H/2}})`);
      g.selectAll("path").data(pie).enter().append("path")
        .attr("d", arc).attr("fill", d => d.data.color)
        .append("title").text(d => `${{d.data.label}}: ${{d.data.value}}`);
      // Legend
      const legend = svg.append("g").attr("transform",`translate(${{r*2 + 20}},10)`);
      data.forEach((d,i) => {{
        legend.append("rect").attr("x",0).attr("y",i*22).attr("width",12).attr("height",12).attr("fill",d.color);
        legend.append("text").attr("x",16).attr("y",i*22+10).style("font-size","12px").text(`${{d.label}} (${{d.value}})`);
      }});
    }}
    drawSentiment("sent1", a1.sentiment_distribution, color1);
    drawSentiment("sent2", a2.sentiment_distribution, color2);

    // Article tables
    function fillTable(tbodyId, articles) {{
      const tbody = document.getElementById(tbodyId);
      (articles || []).slice(0, 15).forEach(a => {{
        const tr = document.createElement("tr");
        const titleCell = document.createElement("td");
        if (a.url) {{
          const link = document.createElement("a");
          link.href = a.url; link.target = "_blank";
          link.textContent = a.title || a.url;
          titleCell.appendChild(link);
        }} else {{
          titleCell.textContent = a.title || "(no title)";
        }}
        const sentCell = document.createElement("td");
        const colors = {{positive:"#4caf50", negative:"#f44336", neutral:"#9e9e9e"}};
        sentCell.textContent = a.sentiment || "—";
        sentCell.style.color = colors[a.sentiment] || "#333";
        const scoreCell = document.createElement("td");
        scoreCell.textContent = (a.score !== undefined) ? (a.score >= 0 ? "+" : "") + a.score : "—";
        tr.append(titleCell, sentCell, scoreCell);
        tbody.appendChild(tr);
      }});
    }}
    fillTable("table1", a1.articles);
    fillTable("table2", a2.articles);
  </script>
</body>
</html>
"""


def generate_dashboard_html(comparison: Dict) -> str:
    """Return a complete HTML dashboard string."""
    a1 = comparison["agency1"]
    a2 = comparison["agency2"]
    # Build a stripped-down comparison without full article content for embedding
    slim = {
        "topic": comparison["topic"],
        "stance_summary": comparison["stance_summary"],
        "overlap_keywords": comparison["overlap_keywords"],
        "agency1": {
            "name": a1["name"],
            "article_count": a1["article_count"],
            "sentiment_distribution": a1["sentiment_distribution"],
            "average_score": a1["average_score"],
            "articles": [
                {k: v for k, v in art.items() if k in ("url", "title", "sentiment", "polarity", "subjectivity", "framing", "tone", "topic_relevance", "score")}
                for art in a1.get("articles", [])
            ],
        },
        "agency2": {
            "name": a2["name"],
            "article_count": a2["article_count"],
            "sentiment_distribution": a2["sentiment_distribution"],
            "average_score": a2["average_score"],
            "articles": [
                {k: v for k, v in art.items() if k in ("url", "title", "sentiment", "polarity", "subjectivity", "framing", "tone", "topic_relevance", "score")}
                for art in a2.get("articles", [])
            ],
        },
    }
    return _DASHBOARD_TEMPLATE.format(
        topic=comparison["topic"],
        agency1=a1["name"],
        agency2=a2["name"],
        comparison_json=_safe_json(slim),
        color1=_COLORS["agency1"],
        color2=_COLORS["agency2"],
    )


# ---------------------------------------------------------------------------
# Save everything
# ---------------------------------------------------------------------------

def save_all(comparison: Dict, output_dir: str = "output") -> None:
    """
    Write all visualization files and the stats JSON to *output_dir*.

    Files created:
    - ``stats.json``
    - ``timeline.html``
    - ``wordcloud.html``
    - ``dashboard.html``
    """
    os.makedirs(output_dir, exist_ok=True)

    # stats.json — strip full article content to keep the file small
    stats = {k: v for k, v in comparison.items() if k not in ("agency1", "agency2")}
    for key in ("agency1", "agency2"):
        entry = comparison[key]
        stats[key] = {k: v for k, v in entry.items() if k != "articles"}

    stats_path = os.path.join(output_dir, "stats.json")
    with open(stats_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)
    logger.info("Saved %s", stats_path)

    for filename, generator in [
        ("timeline.html", generate_timeline_html),
        ("wordcloud.html", generate_wordcloud_html),
        ("dashboard.html", generate_dashboard_html),
    ]:
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(generator(comparison))
        logger.info("Saved %s", path)

    print(f"\n✅  Outputs saved to '{output_dir}/':")
    for name in ("stats.json", "timeline.html", "wordcloud.html", "dashboard.html"):
        print(f"   {os.path.join(output_dir, name)}")
