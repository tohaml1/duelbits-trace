"""Decode deBridge FulfilledOrder events in given Ethereum fill txs for one receiver
and look the order up on the deBridge stats API -> appended to data/debridge_orders.csv"""
import csv
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
import bridges
import chain

recv, *txs = sys.argv[1:]
rows = []
for h in txs:
    for l in chain.bs_tx_logs("eth", h):
        d = l.get("decoded") or {}
        if not d.get("method_call", "").startswith("FulfilledOrder"):
            continue
        p = {x["name"]: x["value"] for x in d["parameters"]}
        if p["order"][8].lower() != recv.lower():
            continue
        oid = p["orderId"]
        full = chain.get_json(f"https://stats-api.dln.trade/api/Orders/{oid}")
        g, k = full["giveOfferWithMetadata"], full["takeOfferWithMetadata"]
        rows.append({
            "protocol": "deBridge", "id": oid, "time": bridges.t(full["createdSrcEventMetadata"]["blockTimeStamp"]),
            "src_chain": bridges.CHAINS.get(str(bridges.sv(g["chainId"])), bridges.sv(g["chainId"])),
            "src_address": bridges.sv(full["makerSrc"]), "src_asset": g["metadata"]["symbol"],
            "src_amount": str(Decimal(bridges.sv(g["amount"])) / Decimal(10 ** int(g["metadata"]["decimals"]))),
            "src_tx": bridges.sv(full["createdSrcEventMetadata"]["transactionHash"]),
            "dst_chain": "ethereum", "dst_address": recv.lower(), "dst_asset": "ETH",
            "dst_amount": str(Decimal(p["actualFulfillAmount"]) / Decimal(10**18)), "dst_tx": h, "status": full.get("state"),
        })
p = os.path.join(os.path.dirname(__file__), "..", "data", "debridge_orders.csv")
with open(p, "a", newline="", encoding="utf-8") as f:
    csv.DictWriter(f, fieldnames=bridges.COLS[:-1]).writerows(rows)
print(len(rows))
