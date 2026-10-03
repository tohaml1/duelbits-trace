"""Resolve cross-chain hops through the bridge/solver APIs the attacker used.

  * deBridge DLN  - stats-api.dln.trade  /api/Orders/filteredList  {"creator": addr}
  * Relay         - api.relay.link        /requests/v2?user=addr
  * THORChain     - midgard.ninerealms.com /v2/actions?address=addr

Each API is the protocol's own public index. Every row it returns is later checked
against the destination chain (the fill tx must exist and pay the stated recipient).
"""
import csv
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import requests

sys.path.insert(0, os.path.dirname(__file__))
import chain

CHAINS = {"1": "ethereum", "56": "bnb", "42161": "arbitrum", "8453": "base", "10": "optimism", "137": "polygon",
          "728126428": "tron", "100000026": "tron", "7565164": "solana", "8253038": "bitcoin", "43114": "avalanche",
          "59144": "linea", "324": "zksync", "100000001": "solana"}


def t(sec):
    return datetime.fromtimestamp(int(sec), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def sv(x):
    if isinstance(x, dict):
        return x.get("stringValue") or x.get("bigIntegerValue")
    return x


def dln_orders(addr):
    rows = []
    r = chain.get_json("https://stats-api.dln.trade/api/Orders/filteredList", method="POST", body={"skip": 0, "take": 100, "creator": addr})
    if "orders" not in r:
        raise RuntimeError(str(r)[:200])
    for o in r.get("orders", []):
        oid = sv(o["orderId"])
        full = chain.get_json(f"https://stats-api.dln.trade/api/Orders/{oid}")
        g, k = full["giveOfferWithMetadata"], full["takeOfferWithMetadata"]
        gd, kd = int(g.get("decimals") or g["metadata"]["decimals"]), int(k.get("decimals") or k["metadata"]["decimals"])
        rows.append({
            "protocol": "deBridge", "id": oid, "time": t(full["createdSrcEventMetadata"]["blockTimeStamp"]),
            "src_chain": CHAINS.get(str(sv(g["chainId"])), sv(g["chainId"])), "src_address": sv(full["makerSrc"]),
            "src_asset": g["metadata"]["symbol"], "src_amount": str(Decimal(sv(g["amount"])) / Decimal(10**gd)),
            "src_tx": sv(full["createdSrcEventMetadata"]["transactionHash"]),
            "dst_chain": CHAINS.get(str(sv(k["chainId"])), sv(k["chainId"])), "dst_address": sv(full["receiverDst"]),
            "dst_asset": k["metadata"]["symbol"], "dst_amount": str(Decimal(sv(full.get("actualFulfillAmount") or k["amount"])) / Decimal(10**kd)),
            "dst_tx": sv((full.get("fulfilledDstEventMetadata") or {}).get("transactionHash")), "status": full.get("state"),
        })
    return rows


def relay_requests(addr):
    rows, cont = [], None
    for _ in range(20):
        params = {"user": addr, "limit": 50}
        if cont:
            params["continuation"] = cont
        r = chain.get_json("https://api.relay.link/requests/v2", params=params)
        for q in r.get("requests", []):
            md = (q.get("data") or {}).get("metadata") or {}
            ci, co = md.get("currencyIn") or {}, md.get("currencyOut") or {}
            itx = ((q.get("data") or {}).get("inTxs") or [{}])[0]
            otx = ((q.get("data") or {}).get("outTxs") or [{}])[0]
            rows.append({
                "protocol": "Relay", "id": q["id"], "time": t(itx.get("timestamp") or 0),
                "src_chain": CHAINS.get(str((ci.get("currency") or {}).get("chainId")), (ci.get("currency") or {}).get("chainId")),
                "src_address": md.get("sender") or q.get("user"), "src_asset": (ci.get("currency") or {}).get("symbol"),
                "src_amount": ci.get("amountFormatted"), "src_tx": itx.get("hash"),
                "dst_chain": CHAINS.get(str((co.get("currency") or {}).get("chainId")), (co.get("currency") or {}).get("chainId")),
                "dst_address": md.get("recipient") or q.get("recipient"), "dst_asset": (co.get("currency") or {}).get("symbol"),
                "dst_amount": co.get("amountFormatted"), "dst_tx": otx.get("hash"), "status": q.get("status"),
            })
        cont = r.get("continuation")
        if not cont:
            break
    return rows


MIDGARD = ["https://midgard.ninerealms.com", "https://midgard.thorchain.liquify.com", "https://midgard.thorswap.net",
           "https://thorchain-midgard.publicnode.com"]


def thor_actions(addr):
    rows, r, err = [], None, None
    for host in MIDGARD:
        try:
            r = chain.get_json(f"{host}/v2/actions", params={"address": addr, "limit": 50})
            break
        except Exception as e:
            err = e
    if r is None:
        raise err
    for a in r.get("actions", []):
        ins, outs = a.get("in", []), a.get("out", [])
        for i in ins:
            for o in outs or [{}]:
                ic = (i.get("coins") or [{}])[0]; oc = (o.get("coins") or [{}])[0]
                rows.append({
                    "protocol": "THORChain", "id": a.get("type"), "time": t(int(a["date"]) // 10**9),
                    "src_chain": (ic.get("asset") or "").split(".")[0], "src_address": i.get("address"),
                    "src_asset": ic.get("asset"), "src_amount": str(Decimal(ic.get("amount", 0)) / Decimal(10**8)),
                    "src_tx": i.get("txID"), "dst_chain": (oc.get("asset") or "").split(".")[0],
                    "dst_address": o.get("address"), "dst_asset": oc.get("asset"),
                    "dst_amount": str(Decimal(oc.get("amount", 0)) / Decimal(10**8)), "dst_tx": o.get("txID"),
                    "status": a.get("status"),
                })
    return rows


COLS = ["protocol", "id", "time", "src_chain", "src_address", "src_asset", "src_amount", "src_tx",
        "dst_chain", "dst_address", "dst_asset", "dst_amount", "dst_tx", "status", "queried_as"]

if __name__ == "__main__":
    outp, *addrs = sys.argv[1:]
    if len(addrs) == 1 and os.path.isfile(addrs[0]):
        addrs = [l.split("#")[0].strip() for l in open(addrs[0]) if l.split("#")[0].strip()]
    allrows, seen = [], set()
    log = []
    for a in addrs:
        for fn in (dln_orders, relay_requests, thor_actions):
            if fn is dln_orders and not a.startswith("0x"):
                continue
            try:
                for r in fn(a):
                    key = (r["protocol"], r["id"], r["src_tx"])
                    if key in seen:
                        continue
                    seen.add(key); r["queried_as"] = a; allrows.append(r)
                log.append(f"ok {fn.__name__} {a[:10]}")
            except Exception as e:
                log.append(f"ERR {fn.__name__} {a[:10]} {type(e).__name__} {str(e)[:120]}")
    allrows.sort(key=lambda r: r["time"])
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    with open(outp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(allrows)
    open(outp + ".log", "w").write("\n".join(log))
