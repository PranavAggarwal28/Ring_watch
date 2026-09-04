"""
generate_report.py

Purpose: build the final demo artifact - a single HTML page you open in
a browser and show to judges. It has two parts:
  1. An interactive graph (drag, zoom, click nodes) showing all accounts,
     with fraud ring clusters highlighted in red.
  2. A dashboard of cards - one per detected ring - showing the severity
     score, evidence, and the AI-generated plain-English explanation.

Run this AFTER detect_rings.py AND explain_rings.py, with:
    python generate_report.py

It reads enriched_results.json (produced by explain_rings.py) and
transactions.csv, and writes everything into the output/ folder.
"""

import json
import os
import pandas as pd
import networkx as nx
from pyvis.network import Network
from detect_rings import load_transactions, build_account_graph, find_clusters

OUTPUT_DIR = "output"
GRAPH_FILE = os.path.join(OUTPUT_DIR, "graph.html")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.html")


def build_graph_visualization(df, clusters):
    """
    Build the interactive graph using pyvis. Think of pyvis as a
    wrapper that takes a networkx graph (the dots-and-lines data
    structure) and turns it into an actual clickable webpage, using
    a JS library under the hood - similar to how you'd use D3.js or
    vis.js directly in a MERN app, except pyvis generates that JS/HTML
    for you from Python.
    """
    G = build_account_graph(df)

    # Flatten all flagged accounts into one set, so we can quickly check
    # "is this account part of a detected ring?" while coloring nodes.
    flagged_accounts = set()
    for cluster in clusters:
        flagged_accounts.update(cluster)

    net = Network(height="600px", width="100%", bgcolor="#111111", font_color="white")

    # physics makes the graph auto-arrange itself so connected nodes
    # cluster together visually - this is what makes rings visually
    # "pop out" as tight little knots separate from the main cloud.
    net.barnes_hut()

    for node in G.nodes():
        if node in flagged_accounts:
            net.add_node(node, label=node, color="#e74c3c", size=20)  # red = flagged
        else:
            net.add_node(node, label=node, color="#3498db", size=10)  # blue = normal

    for source, target in G.edges():
        net.add_edge(source, target)

    net.write_html(GRAPH_FILE)
    print(f"Graph saved to {GRAPH_FILE}")


def build_dashboard_html(enriched_results):
    """
    Build the main report page. This is plain HTML generated as a
    Python string - no framework, no build step. Each cluster becomes
    one "card" of information. The confidence label controls the card's
    color, so high-risk rings visually stand out immediately.
    """
    def severity_color(score):
        """
        Color the card by the severity_score WE compute with transparent
        rules, not by the AI's confidence label. The AI's "high/medium/low"
        is a separate judgment call that can bunch up (e.g. everything
        called "high") even when the underlying scores clearly differ -
        using our own number keeps the visual signal honest and matches
        exactly what we can explain to a judge.
        """
        if score >= 90:
            return "#e74c3c"   # red - very high severity
        elif score >= 60:
            return "#f39c12"   # orange - moderate severity
        else:
            return "#2ecc71"   # green - lower severity

    cards_html = ""
    for i, result in enumerate(enriched_results):
        color = severity_color(result["severity_score"])
        cards_html += f"""
        <div class="card" style="border-left: 6px solid {color};">
            <h2>Cluster {i + 1} &mdash; Severity {result['severity_score']}/100</h2>
            <p class="meta">
                {result['size']} accounts &bull;
                {result['transaction_count']} transactions &bull;
                &#8377;{result['total_amount']:,} total &bull;
                {result['time_span_minutes']} min activity window
            </p>
            <p class="confidence" style="color: {color};">
                Confidence: {result.get('ai_confidence', 'n/a').upper()} &mdash;
                Recommended action: {result.get('ai_recommended_action', 'n/a').replace('_', ' ').upper()}
            </p>
            <p class="explanation">{result.get('ai_explanation', 'No explanation available.')}</p>
            <details>
                <summary>Flagged account IDs</summary>
                <code>{', '.join(result['accounts'])}</code>
            </details>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>RingWatch - Fraud Ring Detection Report</title>
<style>
    body {{ font-family: Arial, sans-serif; background: #1a1a1a; color: #eee; margin: 0; padding: 20px 40px; }}
    h1 {{ color: #fff; }}
    .subtitle {{ color: #aaa; margin-top: -10px; }}
    .card {{ background: #242424; border-radius: 8px; padding: 20px; margin: 20px 0; }}
    .meta {{ color: #999; font-size: 14px; }}
    .confidence {{ font-weight: bold; }}
    .explanation {{ line-height: 1.5; }}
    code {{ color: #7ec8e3; word-break: break-all; }}
    iframe {{ border: none; border-radius: 8px; margin-top: 20px; }}
</style>
</head>
<body>
    <h1>RingWatch</h1>
    <p class="subtitle">Fraud ring detection &mdash; {len(enriched_results)} suspicious cluster(s) found</p>

    <h2>Account Network</h2>
    <p class="meta">Red nodes are flagged accounts. Drag to explore, scroll to zoom.</p>
    <iframe src="graph.html" width="100%" height="620px"></iframe>

    <h2>Flagged Rings</h2>
    {cards_html}
</body>
</html>
"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report saved to {REPORT_FILE}")


def main():
    with open("enriched_results.json") as f:
        enriched_results = json.load(f)

    df = load_transactions()
    G = build_account_graph(df)
    clusters = find_clusters(G)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    build_graph_visualization(df, clusters)
    build_dashboard_html(enriched_results)

    print(f"\nDone. Open {REPORT_FILE} in your browser to view the demo.")


if __name__ == "__main__":
    main()