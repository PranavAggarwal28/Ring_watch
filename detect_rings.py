"""
detect_rings.py

Purpose: read transactions.csv and find groups of accounts that are
SECRETLY connected (sharing a device or IP), without ever looking at the
ring_label answer-key column.

Analogy: this is the "teacher noticing 6 students used the same WiFi"
step. We build a picture (a graph) where each account is a dot, and we
draw a line between two dots if they share a device_id or ip_address.
Groups of dots that are all connected to each other = rings.

Run this AFTER generate_data.py, with:  python detect_rings.py
"""

import pandas as pd
import networkx as nx
from collections import defaultdict

INPUT_FILE = "transactions.csv"

# A cluster smaller than this is probably just coincidence (e.g. 2 family
# members sharing WiFi) rather than an organized ring. Tune this later.
MIN_RING_SIZE = 3


def load_transactions(input_file=INPUT_FILE):
    """Read the CSV into a pandas DataFrame - think of this like loading
    a spreadsheet into memory as a table you can query/filter easily."""
    df = pd.read_csv(input_file)
    return df


def build_account_graph(df):
    """
    Build a graph where:
      - each NODE is an account_id
      - an EDGE (line) connects two accounts if they share a device_id
        OR share an ip_address

    We deliberately do NOT look at ring_label here - that column only
    exists so we can grade ourselves afterwards.
    """
    G = nx.Graph()

    # Add every account as a node first, even ones with no connections yet.
    for account_id in df["account_id"].unique():
        G.add_node(account_id)

    # --- Link accounts that share a device_id ---
    # group all account_ids by device_id, e.g. {"device_A": [acc1, acc2, acc3]}
    device_groups = defaultdict(set)
    for _, row in df.iterrows():
        device_groups[row["device_id"]].add(row["account_id"])

    for device, accounts in device_groups.items():
        accounts = list(accounts)
        if len(accounts) > 1:
            # connect every pair of accounts that shares this device
            for i in range(len(accounts)):
                for j in range(i + 1, len(accounts)):
                    G.add_edge(accounts[i], accounts[j], reason="shared_device")

    # --- Link accounts that share an ip_address ---
    ip_groups = defaultdict(set)
    for _, row in df.iterrows():
        ip_groups[row["ip_address"]].add(row["account_id"])

    for ip, accounts in ip_groups.items():
        accounts = list(accounts)
        if len(accounts) > 1:
            for i in range(len(accounts)):
                for j in range(i + 1, len(accounts)):
                    G.add_edge(accounts[i], accounts[j], reason="shared_ip")

    return G


def find_clusters(G):
    """
    A 'connected component' is networkx's term for: a group of nodes
    that are all reachable from each other by following edges.
    That is EXACTLY our definition of a ring.

    nx.connected_components() does this search for us automatically -
    this one function call replaces what would otherwise be a manual
    graph-traversal algorithm (BFS/DFS) you'd have to write by hand.
    """
    clusters = []
    for component in nx.connected_components(G):
        if len(component) >= MIN_RING_SIZE:
            clusters.append(component)
    return clusters


def score_cluster(cluster, df):
    """
    For each detected cluster, pull out the evidence a human would want
    to see: which device/IP is shared, how many transactions, how tight
    the time window is (a burst of transactions in minutes is far more
    suspicious than the same over 30 days).
    """
    cluster_df = df[df["account_id"].isin(cluster)]

    # IMPORTANT: count UNIQUE ACCOUNTS per device/IP, not transaction rows.
    # Each account has several transactions, so counting rows would say
    # "24 accounts share this device" when really it's 6 accounts each
    # with 4 transactions. groupby+nunique collapses rows down to the
    # number of distinct accounts per device/IP - the number that
    # actually matches len(cluster) and makes sense in the AI prompt.
    shared_devices = cluster_df.groupby("device_id")["account_id"].nunique().sort_values(ascending=False)
    shared_ips = cluster_df.groupby("ip_address")["account_id"].nunique().sort_values(ascending=False)

    timestamps = pd.to_datetime(cluster_df["timestamp"])
    time_span_minutes = (timestamps.max() - timestamps.min()).total_seconds() / 60

    # Simple rule-based severity score (0-100). This is NOT machine
    # learning - it's transparent, explainable arithmetic, which is
    # exactly what Track 02 wants (judges specifically reward being able
    # to explain WHY something scored the way it did).
    score = 0
    if shared_devices.iloc[0] >= len(cluster):
        score += 40  # every account in this cluster shares one device
    if shared_ips.iloc[0] >= len(cluster):
        score += 30  # every account shares one IP too - very suspicious
    if time_span_minutes < 60:
        score += 30  # all activity happened within an hour - bot-like burst
    elif time_span_minutes < 24 * 60:
        score += 15

    return {
        "accounts": sorted(cluster),
        "size": len(cluster),
        "top_device": shared_devices.index[0],
        "top_device_count": int(shared_devices.iloc[0]),
        "top_ip": shared_ips.index[0],
        "top_ip_count": int(shared_ips.iloc[0]),
        "time_span_minutes": round(time_span_minutes, 1),
        "transaction_count": len(cluster_df),
        "total_amount": round(cluster_df["amount"].sum(), 2),
        "severity_score": score,
    }


def main():
    df = load_transactions()
    print(f"Loaded {len(df)} transactions across {df['account_id'].nunique()} accounts.\n")

    G = build_account_graph(df)
    clusters = find_clusters(G)

    print(f"Found {len(clusters)} suspicious cluster(s) "
          f"(min size {MIN_RING_SIZE} accounts):\n")

    results = []
    for i, cluster in enumerate(clusters):
        result = score_cluster(cluster, df)
        results.append(result)
        print(f"--- Cluster {i+1} ---")
        print(f"  Accounts ({result['size']}): {result['accounts']}")
        print(f"  Shared device: {result['top_device']} "
              f"(used by {result['top_device_count']} accounts)")
        print(f"  Shared IP: {result['top_ip']} "
              f"(used by {result['top_ip_count']} accounts)")
        print(f"  Time span of activity: {result['time_span_minutes']} minutes")
        print(f"  Total transactions: {result['transaction_count']}, "
              f"total amount: {result['total_amount']}")
        print(f"  Severity score: {result['severity_score']}/100\n")

    # Quick self-check against the answer key (ring_label) - ONLY for our
    # own sanity-checking while developing, never used in the detection logic above.
    print("--- Self-check against planted answer key ---")
    for i, cluster in enumerate(clusters):
        labels = df[df["account_id"].isin(cluster)]["ring_label"].unique()
        labels = [l for l in labels if l and str(l) != "nan"]
        print(f"Cluster {i+1} matches planted label(s): {labels if labels else 'NONE (false positive?)'}")

    return results


if __name__ == "__main__":
    main()
