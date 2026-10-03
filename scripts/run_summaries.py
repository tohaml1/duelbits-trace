"""Batch driver: python run_summaries.py <chain> <since|-> <out_prefix> addr1 addr2 ..."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import summarize

ch, since, prefix, *addrs = sys.argv[1:]
since = None if since == "-" else since
os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
for a in addrs:
    p = f"{prefix}_{a.lower()[:10]}.txt"
    try:
        open(p, "w", encoding="utf-8").write(summarize.report(ch, a, since))
        print("ok", p[-25:])
    except Exception:
        open(p, "w", encoding="utf-8").write(traceback.format_exc())
        print("ERR", p[-25:])
