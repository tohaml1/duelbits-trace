"""Breadth-first fund-flow trace on an EVM chain.

Rules (kept deliberately simple so a reviewer can audit them):
  * Only real value moves count: native coin and whitelisted tokens
    (see summarize.REAL_TOKENS). Fake "ETH"/"USDT" lookalike tokens are ignored.
  * Transfers below DUST (in ETH-equivalent units for native, token units otherwise)
    are ignored - this is where address-poisoning dust lives.
  * An address is EXPANDED (treated as attacker-controlled) when it is an EOA with
    fewer than MAX_TXS transactions. Contracts and busy EOAs are TERMINALS:
    services such as bridges, DEX routers, mixers or exchange hot wallets.
  * Expansion is forward-only by default (follow the money out). Backward hops
    can be requested for specific seeds to find where inbound funds came from.

Outputs data/<name>_edges.csv and data/<name>_nodes.csv.
"""
import csv
import os
import sys
from collections import deque
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
import chain
import summarize

DUST = {"ETH": Decimal("0.01"), "USDT": Decimal("10"), "USDC": Decimal("10"), "DAI": Decimal("10"),
        "SHIB": Decimal("1000000"), "WETH": Decimal("0.01"), "WBTC": Decimal("0.0005")}
MAX_TXS = 400


def meta(ch, a):
    d = chain.bs_address(ch, a)
    try:
        c = chain.get_json(f"{chain.BLOCKSCOUT[ch]}/addresses/{a}/counters")
    except Exception:
        c = {}
    impl = ",".join((i.get("name") or "") for i in (d.get("implementations") or []))
    tags = ",".join(t.get("display_name", "") for t in (d.get("public_tags") or []))
    return {
        "address": a,
        "is_contract": bool(d.get("is_contract")),
        "name": d.get("name") or "",
        "impl": impl,
        "tags": tags,
        "txs": int(c.get("transactions_count") or 0),
        "balance": Decimal(d.get("coin_balance") or 0) / Decimal(10**18),
    }


def trace(ch, seeds, since, back_seeds=(), max_nodes=150):
    nodes, edges, seen = {}, [], set()
    q = deque((s.lower(), "fwd", 0) for s in seeds)
    q.extend((s.lower(), "back", 0) for s in back_seeds)
    while q and len(nodes) < max_nodes:
        a, mode, depth = q.popleft()
        if (a, mode) in seen:
            continue
        seen.add((a, mode))
        if a not in nodes:
            nodes[a] = meta(ch, a)
            nodes[a]["depth"] = depth
        m = nodes[a]
        expand = (not m["is_contract"]) and m["txs"] < MAX_TXS
        m["role"] = "expanded" if expand else "terminal"
        if not expand and depth > 0:
            continue
        for ts, d, cp, cpmeta, asset, v, h in summarize.flows(ch, a, since):
            base = asset.replace("(int)", "")
            if v < DUST.get(base, Decimal(0)):
                continue
            if d == "out":
                edges.append((ts, a, cp, base, v, h))
                if mode == "fwd":
                    q.append((cp, "fwd", depth + 1))
            elif d == "in" and mode == "back":
                edges.append((ts, cp, a, base, v, h))
                q.append((cp, "back", depth + 1))
    # make sure every edge endpoint has metadata
    for e in edges:
        for x in (e[1], e[2]):
            if x not in nodes:
                nodes[x] = meta(ch, x)
                nodes[x]["depth"] = None
                nodes[x]["role"] = "unvisited"
    return nodes, sorted(set(edges))


def write(name, nodes, edges):
    root = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, f"{name}_edges.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "from", "to", "asset", "amount", "tx_hash"])
        for e in edges:
            w.writerow([e[0], e[1], e[2], e[3], f"{e[4]:f}", e[5]])
    with open(os.path.join(root, f"{name}_nodes.csv"), "w", newline="", encoding="utf-8") as f:
        cols = ["address", "role", "depth", "is_contract", "name", "impl", "tags", "txs", "balance"]
        w = csv.writer(f)
        w.writerow(cols)
        for n in nodes.values():
            w.writerow([n.get(c, "") for c in cols])


if __name__ == "__main__":
    # usage: trace_evm.py <chain> <name> <since> <fwd_seeds,comma> [back_seeds,comma]
    ch, name, since, fwd = sys.argv[1:5]
    back = sys.argv[5].split(",") if len(sys.argv) > 5 else []
    nodes, edges = trace(ch, [s for s in fwd.split(",") if s], since, back)
    write(name, nodes, edges)
    print(len(nodes), "nodes", len(edges), "edges")
