"""deBridge orders created by the attacker -> data/debridge_orders.csv"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bridges

rows = []
for a in sys.argv[1:]:
    rows += bridges.dln_orders(a)
p = os.path.join(os.path.dirname(__file__), "..", "data", "debridge_orders.csv")
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=bridges.COLS[:-1]); w.writeheader(); w.writerows(sorted(rows, key=lambda r: r["time"]))
print(len(rows))
