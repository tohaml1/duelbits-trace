"""Bitcoin leg: history of the BTC address named as refund address in the Chainflip swaps.
Writes data/btc_leg.csv (one row per tx: inputs/outputs touching the address)."""
import csv
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(__file__))
import chain

addr = sys.argv[1]
rows = []
for t in chain.btc_txs(addr):
    ts = datetime.fromtimestamp(t["status"].get("block_time", 0), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    ins = [(v["prevout"]["scriptpubkey_address"], D(v["prevout"]["value"]) / D(10**8)) for v in t["vin"] if v.get("prevout")]
    outs = [(v.get("scriptpubkey_address"), D(v["value"]) / D(10**8)) for v in t["vout"]]
    mine_in = sum((v for a, v in ins if a == addr), D(0)); mine_out = sum((v for a, v in outs if a == addr), D(0))
    rows.append({"time": ts, "txid": t["txid"], "net_btc": f"{mine_out - mine_in:f}",
                 "inputs": ";".join(f"{a}:{v:f}" for a, v in ins), "outputs": ";".join(f"{a}:{v:f}" for a, v in outs)})
rows.sort(key=lambda r: r["time"])
p = os.path.join(os.path.dirname(__file__), "..", "data", "btc_leg.csv")
with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["time", "txid", "net_btc", "inputs", "outputs"]); w.writeheader(); w.writerows(rows)
print(len(rows), chain.btc_address(addr)["chain_stats"])
