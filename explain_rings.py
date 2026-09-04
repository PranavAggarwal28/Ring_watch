"""
explain_rings.py

Purpose: take the clusters that detect_rings.py already found (using pure
Python logic, no AI) and ask Gemini to turn each one into a plain-English
risk writeup a non-technical reviewer could act on immediately.

Important: the AI is NOT doing the detection. detect_rings.py already
decided which accounts are suspicious using graph logic. All we're
handing to Gemini is a small structured summary of each cluster - not
raw transaction data - and asking it to explain and recommend an action.

Run this AFTER detect_rings.py, with:  python explain_rings.py

Before running, set your API key as an environment variable (don't paste
the key directly into your code - same rule as never committing a .env
file to git in your MERN projects). Get a free key (no credit card) at
aistudio.google.com -> "Get API key":

    export GOOGLE_API_KEY="your-key-here"      (Mac/Linux)
    setx GOOGLE_API_KEY "your-key-here"         (Windows)
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from detect_rings import load_transactions, build_account_graph, find_clusters, score_cluster

load_dotenv()
# The client object is like an axios instance you'd configure once in a
# JS project - it reads your API key from the environment automatically.
client = genai.Client()

MODEL = "gemini-3.6-flash"  # free tier, fast, good enough for this task


def cached_explanation(cluster_result):
    """Use a prior genuine Gemini response only for an exact evidence match."""
    cache_file = Path(__file__).with_name("enriched_results.json")
    if not cache_file.is_file():
        return None
    try:
        cached_results = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    evidence_keys = ("accounts", "size", "top_device", "top_device_count", "top_ip",
                     "top_ip_count", "time_span_minutes", "transaction_count",
                     "total_amount", "severity_score")
    for cached in cached_results:
        if all(cached.get(key) == cluster_result.get(key) for key in evidence_keys):
            if all(cached.get(key) for key in ("ai_explanation", "ai_confidence", "ai_recommended_action")):
                return {"explanation": cached["ai_explanation"], "confidence": cached["ai_confidence"], "recommended_action": cached["ai_recommended_action"]}
    return None


def build_prompt(cluster_result):
    """
    Turn one cluster's structured signals into a prompt for Claude.
    We're deliberately NOT sending raw transaction rows - just the
    summary detect_rings.py already computed. Smaller, cheaper, and
    keeps the AI's job scoped to "explain this", not "find patterns".
    """
    return f"""You are a fraud risk analyst assistant for a payments company.
You will be given structured signals about a cluster of accounts that a
rule-based detection system has already flagged as a suspected fraud ring.

Do NOT invent facts beyond what is given. Base your explanation only on
the signals below.

Cluster signals:
- Number of accounts in cluster: {cluster_result['size']}
- Accounts sharing one device: {cluster_result['top_device_count']} out of {cluster_result['size']}
- Accounts sharing one IP address: {cluster_result['top_ip_count']} out of {cluster_result['size']}
- Time span of all activity: {cluster_result['time_span_minutes']} minutes
- Total transactions: {cluster_result['transaction_count']}
- Total transaction amount: {cluster_result['total_amount']}
- Rule-based severity score (0-100): {cluster_result['severity_score']}

Respond with ONLY valid JSON, no other text, no markdown code fences,
in exactly this shape:
{{
  "explanation": "2-3 sentences explaining in plain English why this looks like a fraud ring, referencing the specific signals above",
  "confidence": "low" | "medium" | "high",
  "recommended_action": "monitor" | "manual_review" | "block_and_investigate"
}}"""


def explain_cluster(cluster_result):
    """
    Make one API call to Gemini for one cluster, and parse the JSON
    response. This is the same shape as calling any REST API from JS
    with fetch() - request in, JSON back.
    """
    response = client.models.generate_content(
        model=MODEL,
        contents=build_prompt(cluster_result),
    )

    # response.text holds the model's plain text reply.
    raw_text = response.text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback in case the model wraps output in markdown fences
        # despite instructions - strip them and retry once.
        cleaned = raw_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)

    return parsed


def run_pipeline(input_file=None, output_file=None):
    """Run the established detection + Gemini explanation workflow.

    Optional paths make the pipeline reusable by the web app while retaining
    the original command-line behaviour and default output file.
    """
    df = load_transactions(input_file) if input_file else load_transactions()
    G = build_account_graph(df)
    clusters = find_clusters(G)

    enriched_results = []

    for i, cluster in enumerate(clusters):
        cluster_result = score_cluster(cluster, df)
        print(f"Explaining cluster {i+1} of {len(clusters)}...")

        try:
            ai_output = explain_cluster(cluster_result)
        except Exception:
            # Never invent text for another CSV. The bundled sample alone can
            # reuse its exact, previously generated Gemini explanation.
            ai_output = cached_explanation(cluster_result)
            if ai_output is None:
                raise
        cluster_result["ai_explanation"] = ai_output["explanation"]
        cluster_result["ai_confidence"] = ai_output["confidence"]
        cluster_result["ai_recommended_action"] = ai_output["recommended_action"]

        enriched_results.append(cluster_result)

        print(f"  Confidence: {ai_output['confidence']}")
        print(f"  Recommended action: {ai_output['recommended_action']}")
        print(f"  Explanation: {ai_output['explanation']}\n")

    # Save enriched results to JSON so generate_report.py can pick them
    # up next without re-running detection and re-calling the API.
    destination = output_file or "enriched_results.json"
    with open(destination, "w", encoding="utf-8") as f:
        json.dump(enriched_results, f, indent=2)

    print(f"Saved {len(enriched_results)} enriched cluster(s) to {destination}")
    return enriched_results


def main():
    return run_pipeline()


if __name__ == "__main__":
    main()
    
