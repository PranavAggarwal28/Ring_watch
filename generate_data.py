"""
generate_data.py

Purpose: create a fake (synthetic) transactions.csv file that looks like
real payment data, but with a few "fraud rings" secretly planted inside it.

Think of this like writing a seed/fixture script for a database in a MERN
app - except instead of inserting rows into MongoDB, we're writing rows
into a CSV file that our next script will read.

Run this file with:  python generate_data.py
It will create a file called transactions.csv in the same folder.
"""

import random
import csv
from datetime import datetime, timedelta
from faker import Faker

# Faker is a library that generates realistic fake data (names, IDs, etc.)
# Think of it like a library version of a JS mock-data generator (e.g. faker.js
# in the JS world - same idea, same name, different language).
fake = Faker()

# Setting a random "seed" makes the randomness repeatable - every time you
# run this script you'll get the SAME fake data. Useful while developing,
# so your detection code isn't chasing a moving target.
random.seed(42)
Faker.seed(42)

# ---------------------------------------------------------------------------
# STEP 1: Config - change these numbers to make more/less data
# ---------------------------------------------------------------------------
NUM_NORMAL_ACCOUNTS = 200      # innocent, unrelated accounts (background noise)
NUM_RINGS = 3                  # how many fraud rings to plant
RING_SIZE = 6                  # how many accounts per ring
TRANSACTIONS_PER_ACCOUNT = 4   # how many transactions each account makes

OUTPUT_FILE = "transactions.csv"


def random_timestamp(start_days_ago=30):
    """Returns a random datetime within the last `start_days_ago` days."""
    now = datetime.now()
    random_seconds = random.randint(0, start_days_ago * 24 * 60 * 60)
    return now - timedelta(seconds=random_seconds)


def make_normal_account():
    """
    Creates one 'innocent' account with its OWN unique device and IP.
    Real users each use their own phone/laptop and their own IP - that's
    what makes them look different from a ring later.
    """
    return {
        "account_id": fake.uuid4()[:8],
        "device_id": fake.uuid4()[:12],   # unique device per normal account
        "ip_address": fake.ipv4(),        # unique IP per normal account
    }


def make_fraud_ring(ring_index, size):
    """
    Creates a group of accounts that all SHARE the same device_id and/or
    ip_address. This is the "tell" our detection script will look for later -
    real independent users almost never share a device or IP with 5 other
    "different" people.
    """
    shared_device = fake.uuid4()[:12]
    shared_ip = fake.ipv4()
    fake_accounts = []
    for _ in range(size):
        fake_accounts.append({
            "account_id": fake.uuid4()[:8],
            "device_id": shared_device,   # <- SAME for every account in this ring
            "ip_address": shared_ip,      # <- SAME for every account in this ring
            "ring_label": f"ring_{ring_index}",  # not real data - just so
                                                   # WE (the developers) know
                                                   # the answer key for testing
        })
    return fake_accounts


def make_transactions_for_account(account):
    """
    Given one account, generate a handful of transactions for it.
    Ring accounts get transactions clustered close together in time
    (that's the "coordinated burst" signal) and normal accounts get
    naturally spread-out random timestamps.
    """
    transactions = []
    is_ring = "ring_label" in account

    if is_ring:
        # pick one "burst window" - all this ring's transactions happen
        # close together, like a bot script firing them off quickly
        burst_start = random_timestamp()
    for i in range(TRANSACTIONS_PER_ACCOUNT):
        if is_ring:
            # transactions seconds/minutes apart - suspiciously fast
            ts = burst_start + timedelta(seconds=random.randint(1, 180))
            amount = round(random.uniform(500, 2000), 2)  # similar amounts
        else:
            ts = random_timestamp()
            amount = round(random.uniform(50, 5000), 2)

        transactions.append({
            "transaction_id": fake.uuid4()[:10],
            "account_id": account["account_id"],
            "device_id": account["device_id"],
            "ip_address": account["ip_address"],
            "amount": amount,
            "timestamp": ts.isoformat(),
            # we keep ring_label ONLY for our own later evaluation
            # (checking "did my detector actually find the planted rings?")
            "ring_label": account.get("ring_label", ""),
        })
    return transactions


def main():
    all_accounts = []

    # Build normal (innocent) accounts
    for _ in range(NUM_NORMAL_ACCOUNTS):
        all_accounts.append(make_normal_account())

    # Build fraud ring accounts
    for i in range(NUM_RINGS):
        all_accounts.extend(make_fraud_ring(i, RING_SIZE))

    # Turn every account into a handful of transactions
    all_transactions = []
    for account in all_accounts:
        all_transactions.extend(make_transactions_for_account(account))

    # Shuffle so rings aren't sitting neatly together in the file -
    # your detection script has to actually find them, not just read
    # them off in planted order.
    random.shuffle(all_transactions)

    # Write to CSV - same idea as writing rows to a spreadsheet.
    fieldnames = ["transaction_id", "account_id", "device_id",
                  "ip_address", "amount", "timestamp", "ring_label"]

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_transactions)

    print(f"Generated {len(all_transactions)} transactions "
          f"({len(all_accounts)} accounts, {NUM_RINGS} planted rings) "
          f"-> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
