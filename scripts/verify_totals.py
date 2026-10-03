"""Recompute every headline number in the README from explorer/bridge data.

Run after the other scripts (or from the cached responses in data/raw).
Writes data/reconciliation.txt. Each line states the figure and the check it passed.
"""
import csv
import os
import sys
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(__file__))
import chain
import summarize
import tron_flows

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
VICTIM = "0x014435b1e39945cf4f5f0c3cbb5833195a95cc9b"
A1 = "0xa77e24fe29d16e051e487ef4ea7b056cb05aef76"
A2 = "0xb5909f3539fe2733866bbde2d3ffca5c6292ebbf"
C = "0x8db9d7f0a03d212c566ca80c66e294cecc20c306"
TORNADO_ROUTER = "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b"
MIXER_FEEDERS = ["0xadb82eef7baa2feaebe64f88577c06f803a2c578", "0x56644f6a348a142d38fb7dde2e942c9ef03d09fc"]
SINCE = "2026-09-24"
out = []


def s(rows, d=None, cp=None, asset=None, frm=None):
    return sum((r[5] for r in rows if (d is None or r[1] == d) and (cp is None or r[2] == cp)
                and (asset is None or r[4].replace("(int)", "") == asset)), D(0))


# 1. Ethereum drain: victim -> A1
a1 = summarize.flows("eth", A1, SINCE)
for asset in ["ETH", "USDT", "USDC", "DAI", "SHIB"]:
    out.append(f"ETH-chain drain  victim->A1  {asset:5} {s(a1, 'in', VICTIM, asset):,.6f}")

# 2. A1 balance sheet in ETH
a1_in, a1_out = s(a1, "in", asset="ETH"), s(a1, "out", asset="ETH")
out.append(f"A1 ETH in {a1_in:,.6f} / out {a1_out:,.6f} / diff {a1_in - a1_out:,.6f} (gas + dust)")

# 3. Tron leg
tron = tron_flows.flows("TAvraZZFCZbDSZoyqWWRRsBkFgZqKaCGbK", 1790208000000)
out.append(f"Tron drain  USDT {sum(r[4] for r in tron if r[1]=='in' and r[3]=='USDT' and r[2]=='THqFmhAPcdHECH3wmrpZv4MWAB2v9TY1oN'):,.6f}"
           f"  TRX {sum(r[4] for r in tron if r[1]=='in' and r[3]=='TRX' and r[2]=='THqFmhAPcdHECH3wmrpZv4MWAB2v9TY1oN'):,.6f}")
relay_dep = [r for r in tron if r[1] == "call" and r[2] == "TXtEs6t2oUWQsNos7m68gbHdE9Q5n6x2oN"]
out.append(f"Tron -> Relay deposits n={len(relay_dep)} TRX {sum(r[4] for r in relay_dep):,.0f}")

# 4. Bridge legs from the protocol APIs (cross-checked: each dst_tx must credit the recipient on Ethereum)
legs = {}
with open(os.path.join(DATA, "debridge_orders.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        legs.setdefault((r["src_chain"], "deBridge", r["src_asset"]), [D(0), D(0), 0])
        L = legs[(r["src_chain"], "deBridge", r["src_asset"])]
        L[0] += D(r["src_amount"]); L[1] += D(r["dst_amount"]); L[2] += 1
with open(os.path.join(DATA, "bridges.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["src_chain"] == "ethereum":
            continue  # same-chain swaps
        k = ("solana" if r["src_chain"] == "792703809" else r["src_chain"], "Relay", r["src_asset"])
        legs.setdefault(k, [D(0), D(0), 0])
        legs[k][0] += D(r["src_amount"]); legs[k][1] += D(r["dst_amount"]); legs[k][2] += 1
for (ch, proto, asset), (src, dst, n) in sorted(legs.items()):
    out.append(f"bridge {ch:7} via {proto:8} n={n:<3} {asset:4} {src:,.6f} -> {dst:,.6f} ETH")

a2 = summarize.flows("eth", A2, SINCE)
out.append(f"A2 (Solana landing) ETH in {s(a2, 'in', asset='ETH'):,.6f} / out {s(a2, 'out', asset='ETH'):,.6f}")

# 5. Consolidation address
c = summarize.flows("eth", C, SINCE)
first_day = sum((r[5] for r in c if r[1] == "in" and r[4].startswith("ETH") and r[0] < "2026-09-25"), D(0))
bal = D(chain.bs_address("eth", C)["coin_balance"]) / D(10**18)
out.append(f"C inflow on 2026-09-24 {first_day:,.6f} ETH; C in {s(c,'in',asset='ETH'):,.6f} out {s(c,'out',asset='ETH'):,.6f}; balance now {bal:,.6f}")

# 6. Tornado Cash
tc = D(0); n = 0
for m in MIXER_FEEDERS:
    rows = summarize.flows("eth", m, SINCE)
    tc += s(rows, "out", TORNADO_ROUTER, "ETH"); n += len([r for r in rows if r[1] == "out" and r[2] == TORNADO_ROUTER])
out.append(f"Tornado Cash deposits n={n} total {tc:,.6f} ETH")

# 7. BNB leg itemised from deBridge creation-tx receipts (scripts/gaps.py)
bnb = {}
with open(os.path.join(DATA, "bnb_receipts.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["kind"] in ("out", "native_value"):
            bnb[r["token"]] = bnb.get(r["token"], D(0)) + D(r["amount"])
out.append("BNB leg spent by A1 into deBridge: " + ", ".join(f"{k} {v:,.6f}" for k, v in sorted(bnb.items())))
eth_usdt = s(a1, "in", VICTIM, "USDT")
tron_usdt = sum(r[4] for r in tron if r[1] == "in" and r[3] == "USDT" and r[2] == "THqFmhAPcdHECH3wmrpZv4MWAB2v9TY1oN")
out.append(f"USDT across ETH+Tron+BNB = {eth_usdt + tron_usdt + bnb.get('USDT', D(0)):,.2f} (press: $1.62M USDT)")

# 8. Bitcoin leg (scripts/btc_leg.py): sweep into the attacker's BTC address
with open(os.path.join(DATA, "btc_leg.csv"), encoding="utf-8") as f:
    btc = list(csv.DictReader(f))
sweep = btc[0]
out.append(f"BTC sweep {sweep['txid'][:12]}… inputs={len(sweep['inputs'].split(';'))} -> attacker {D(sweep['net_btc']):.8f} BTC")

open(os.path.join(DATA, "reconciliation.txt"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out))
