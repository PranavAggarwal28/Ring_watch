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
RING_SIZE = 6                  # how many accounts per ring
TRANSACTIONS_PER_ACCOUNT = 4   # how many transactions each account makes

# Instead of NUM_RINGS being identical copies, we now define a MIX of ring
# "types" with different levels of obviousness - real fraud rings vary in
# sloppiness, and your severity score should reflect that variety instead
# of always maxing out at 100.
#
#   "obvious"        -> shares device AND ip, tight burst (<1 hr)   -> ~100
#   "device_only"     -> shares device, but DIFFERENT ips per account,
#                        spread over a day                          -> ~55
#   "slow_burn"       -> shares device AND ip, but spread over
#                        several hours instead of minutes            -> ~70
RING_TYPES = ["obvious", "device_only", "slow_burn"]

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


def make_fraud_ring(ring_index, size, ring_type):
    """
    Creates a group of accounts with a "tell" connecting them - but HOW
    obvious that tell is depends on ring_type. This mirrors real fraud:
    some rings are lazy/obvious, others are more careful and only leak
    one signal instead of three.
    """
    shared_device = fake.uuid4()[:12]
    shared_ip = fake.ipv4()
    accounts = []

    for _ in range(size):
        if ring_type == "device_only":
            # Careful ring: shares a device (e.g. same physical phone
            # used to register accounts) but each account connects from
            # a DIFFERENT ip (e.g. different home wifi/mobile data) -
            # only one signal leaks instead of two.
            account_ip = fake.ipv4()
        else:
            # "obvious" and "slow_burn" rings share both device and ip.
            account_ip = shared_ip

        accounts.append({
            "account_id": fake.uuid4()[:8],
            "device_id": shared_device,
            "ip_address": account_ip,
            "ring_label": f"ring_{ring_index}_{ring_type}",  # answer key only
            "ring_type": ring_type,
        })
    return accounts


def make_transactions_for_account(account, ring_burst_start=None):
    """
    Given one account, generate a handful of transactions for it.
    Ring accounts get transactions clustered close together in time
    (that's the "coordinated burst" signal) and normal accounts get
    naturally spread-out random timestamps.

    ring_burst_start: for ring accounts, this is passed in from OUTSIDE
    (shared by the whole ring) rather than picked fresh per account -
    otherwise each ring member gets its own random window and the ring's
    overall time span balloons to weeks instead of minutes.

    The WIDTH of that burst window depends on ring_type:
    "obvious"/"device_only" rings burst within ~3 minutes (bot-like);
    "slow_burn" rings spread activity across several hours, still
    coordinated but not tight enough to trip the "under 60 min" rule -
    that's what makes them score lower and harder to catch.
    """
    transactions = []
    is_ring = "ring_label" in account
    ring_type = account.get("ring_type")
    burst_start = ring_burst_start

    for i in range(TRANSACTIONS_PER_ACCOUNT):
        if is_ring:
            if ring_type == "slow_burn":
                # spread across ~4 hours instead of ~3 minutes
                ts = burst_start + timedelta(seconds=random.randint(1, 4 * 60 * 60))
            else:
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

    # Build one fraud ring PER TYPE (obvious, device_only, slow_burn),
    # each remembering its own shared burst-start time.
    ring_burst_starts = {}
    for i, ring_type in enumerate(RING_TYPES):
        ring_accounts = make_fraud_ring(i, RING_SIZE, ring_type)
        all_accounts.extend(ring_accounts)
        ring_burst_starts[f"ring_{i}_{ring_type}"] = random_timestamp()

    # Turn every account into a handful of transactions
    all_transactions = []
    for account in all_accounts:
        burst_start = ring_burst_starts.get(account.get("ring_label"))
        all_transactions.extend(make_transactions_for_account(account, burst_start))

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
          f"({len(all_accounts)} accounts, {len(RING_TYPES)} planted rings "
          f"of types {RING_TYPES}) -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()