"""Flow summary for a Tron address: native TRX transfers + canonical USDT-TRC20 only.

TronGrid's /transactions endpoint returns raw contracts; we decode TransferContract
(TRX) and TriggerSmartContract calls (used for bridge deposits). TRC20 transfers come
from /transactions/trc20 and are filtered to the canonical USDT contract to drop the
fake-token spam that Tron addresses also receive.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
import chain

USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def hex_to_b58(h):
    import hashlib
    b = bytes.fromhex(h)
    chk = hashlib.sha256(hashlib.sha256(b).digest()).digest()[:4]
    n = int.from_bytes(b + chk, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return s


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def flows(addr, since_ms=0):
    rows = []
    for t in chain.tron_txs(addr, min_timestamp=since_ms):
        if (t.get("ret") or [{}])[0].get("contractRet") not in ("SUCCESS", None):
            continue
        for c in t["raw_data"]["contract"]:
            v = c["parameter"]["value"]
            owner = hex_to_b58(v["owner_address"]) if "owner_address" in v else ""
            if c["type"] == "TransferContract":
                to = hex_to_b58(v["to_address"])
                amt = Decimal(v["amount"]) / Decimal(10**6)
                d = "out" if owner == addr else "in"
                rows.append((ts(t["block_timestamp"]), d, to if d == "out" else owner, "TRX", amt, t["txID"]))
            elif c["type"] == "TriggerSmartContract" and owner == addr:
                cv = Decimal(v.get("call_value", 0)) / Decimal(10**6)
                ca = hex_to_b58(v["contract_address"])
                rows.append((ts(t["block_timestamp"]), "call", ca, "TRX", cv, t["txID"]))
    for t in chain.tron_trc20(addr, min_timestamp=since_ms, contract_address=USDT_TRC20):
        amt = Decimal(t["value"]) / Decimal(10 ** int(t["token_info"]["decimals"]))
        d = "out" if t["from"] == addr else "in"
        rows.append((ts(t["block_timestamp"]), d, t["to"] if d == "out" else t["from"], "USDT", amt, t["transaction_id"]))
    rows.sort()
    return rows


def report(addr, since_ms=0):
    rows = flows(addr, since_ms)
    agg = defaultdict(lambda: [Decimal(0), 0, None, None])
    for t, d, cp, a, v, h in rows:
        k = (d, cp, a)
        agg[k][0] += v; agg[k][1] += 1; agg[k][2] = agg[k][2] or t; agg[k][3] = t
    acct = chain.tron_account(addr).get("data") or [{}]
    bal = Decimal(acct[0].get("balance", 0)) / Decimal(10**6) if acct else 0
    L = [f"# tron:{addr} balance={bal} TRX", ""]
    for (d, cp, a), (v, n, t0, t1) in sorted(agg.items(), key=lambda kv: (kv[0][0], -kv[1][0])):
        L.append(f"{d:4} {a:4} {v:>20.6f} n={n:<4} {cp} [{t0} .. {t1}]")
    L += ["", "## rows"] + [f"{t} {d:4} {a:4} {v:>20.6f} {cp} {h}" for t, d, cp, a, v, h in rows]
    return "\n".join(L)


if __name__ == "__main__":
    outp = sys.argv[1]
    since = int(datetime(2026, 9, 20, tzinfo=timezone.utc).timestamp() * 1000)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for a in sys.argv[2:]:
            try:
                f.write(report(a, since) + "\n\n")
            except Exception as e:
                import traceback
                f.write(f"# {a} ERR\n{traceback.format_exc()}\n\n")
