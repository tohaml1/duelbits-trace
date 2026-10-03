"""Close two gaps:
  1. BNB leg: decode receipts of the 7 deBridge order-creation txs on BNB Chain
     (what tokens A1 spent before bridging) -> data/bnb_receipts.csv
  2. BTC candidate: inspect the 'Vault' contract and its three payouts to A6
     -> work/vault.json
"""
import csv
import json
import os
import sys
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(__file__))
import bsc_logs
import chain

ROOT = os.path.join(os.path.dirname(__file__), "..")
A1 = "0xa77e24fe29d16e051e487ef4ea7b056cb05aef76"

# ---- 1. BNB receipts
rows = []
with open(os.path.join(ROOT, "data", "debridge_orders.csv"), encoding="utf-8") as f:
    src = [r for r in csv.DictReader(f) if r["src_chain"] == "bnb"]
for r in src:
    rc = chain.bsc_rpc("eth_getTransactionReceipt", [r["src_tx"]])
    tx = chain.bsc_rpc("eth_getTransactionByHash", [r["src_tx"]])
    native = D(int(tx["value"], 16)) / D(10**18)
    rows.append({"src_tx": r["src_tx"], "kind": "native_value", "token": "BNB", "from": tx["from"], "to": tx["to"], "amount": str(native)})
    for l in rc["logs"]:
        if l["topics"] and l["topics"][0] == bsc_logs.TRANSFER and len(l["topics"]) == 3:
            frm, to = "0x" + l["topics"][1][-40:], "0x" + l["topics"][2][-40:]
            if A1 not in (frm, to):
                continue
            sym, dec = bsc_logs.KNOWN.get(l["address"].lower(), (l["address"].lower(), 18))
            rows.append({"src_tx": r["src_tx"], "kind": "out" if frm == A1 else "in", "token": sym, "from": frm, "to": to,
                         "amount": str(D(int(l["data"], 16)) / D(10**dec))})
with open(os.path.join(ROOT, "data", "bnb_receipts.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["src_tx", "kind", "token", "from", "to", "amount"]); w.writeheader(); w.writerows(rows)
tot = {}
for x in rows:
    if x["kind"] in ("out", "native_value"):
        tot[x["token"]] = tot.get(x["token"], D(0)) + D(x["amount"])
print("BNB spent by A1 per token:", {k: f"{v:f}" for k, v in tot.items()})

# ---- 2. Vault
V = "0xf5e10380213880111522dd0efd3dbb45b9f62bcc"
out = {"address": chain.bs_address("eth", V)}
try:
    sc = chain.get_json(f"{chain.BLOCKSCOUT['eth']}/smart-contracts/{V}")
    out["contract"] = {k: sc.get(k) for k in ["name", "compiler_version", "is_verified", "verified_at"]}
    srcc = sc.get("source_code") or ""
    out["source_head"] = srcc[:1500]
except Exception as e:
    out["contract"] = f"ERR {e}"
txs = ["0x42fb0ae995af65ba9c7b2705286a9749b601f31cd1f1c4286c5cc830e1c3878b",
       "0x80ac54af9111cccd275fa89aad7921e1a9251f03691c986656f5afd94c75fc6b",
       "0x259b5d3e0ef54479cf5508a3bcdb2fd96c6de0a2d84dd1efebaaf62d740c321e"]
out["payouts"] = []
for h in txs:
    t = chain.bs_tx("eth", h)
    logs = chain.bs_tx_logs("eth", h)
    out["payouts"].append({
        "hash": h, "from": t["from"]["hash"], "to": (t.get("to") or {}).get("hash"), "method": t.get("method"),
        "decoded_input": t.get("decoded_input"), "raw_input_head": (t.get("raw_input") or "")[:600],
        "logs": [{"addr": l["address"]["hash"], "decoded": l.get("decoded"), "data_head": (l.get("data") or "")[:300]} for l in logs],
    })
caller = out["payouts"][0]["from"]
out["caller_meta"] = {k: chain.bs_address("eth", caller).get(k) for k in ["name", "is_contract", "public_tags"]}
os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "work", "vault.json"), "w"), indent=1, default=str)
print("vault done")
