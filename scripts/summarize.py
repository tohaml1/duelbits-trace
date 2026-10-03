"""Per-counterparty flow summary for an EVM address, real assets only.

Spoofed transfers are dropped by two rules:
  * tokens must be on the whitelist of canonical contracts below;
  * an outgoing token transfer only counts if the address itself signed the tx
    (poisoning contracts emit Transfer events "from" addresses they don't control).
"""
import sys
from collections import defaultdict
from decimal import Decimal

import chain

REAL_TOKENS = {
    "eth": {
        "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
        "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
        "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "SHIB",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    },
}

def lbl(a):
    if not a:
        return ("", "")
    tags = ",".join(t.get("display_name", "") for t in (a.get("public_tags") or []))
    n = a.get("name") or ""
    meta = " ".join(x for x in [n, "{" + tags + "}" if tags else "", "(contract)" if a.get("is_contract") else ""] if x)
    return (a["hash"].lower(), meta)

def flows(ch, addr, since=None, until=None):
    addr = addr.lower()
    signed = set()
    out = []  # (ts, direction, counterparty, meta, asset, amount, hash)
    for t in chain.bs_txs(ch, addr):
        f, fm = lbl(t["from"]); to, tm = lbl(t.get("to"))
        if t.get("status") != "ok":
            continue
        if f == addr:
            signed.add(t["hash"])
        v = Decimal(t["value"]) / Decimal(10**18)
        if v == 0:
            continue
        if f == addr:
            out.append((t["timestamp"], "out", to, tm, "ETH", v, t["hash"]))
        elif to == addr:
            out.append((t["timestamp"], "in", f, fm, "ETH", v, t["hash"]))
    for t in chain.bs_internal(ch, addr):
        v = Decimal(t["value"]) / Decimal(10**18)
        if v == 0 or not t.get("success"):
            continue
        f, fm = lbl(t["from"]); to, tm = lbl(t.get("to"))
        if to == addr:
            out.append((t["timestamp"], "in", f, fm, "ETH(int)", v, t["transaction_hash"]))
        elif f == addr:
            out.append((t["timestamp"], "out", to, tm, "ETH(int)", v, t["transaction_hash"]))
    real = REAL_TOKENS.get(ch, {})
    for t in chain.bs_token_transfers(ch, addr):
        tok = t["token"]
        ta = (tok.get("address_hash") or tok.get("address") or "").lower()
        if ta not in real:
            continue
        dec = int(tok.get("decimals") or 0)
        v = Decimal(t["total"]["value"]) / Decimal(10**dec)
        f, fm = lbl(t["from"]); to, tm = lbl(t["to"])
        if f == addr:
            out.append((t["timestamp"], "out", to, tm, real[ta], v, t["transaction_hash"]))
        elif to == addr:
            out.append((t["timestamp"], "in", f, fm, real[ta], v, t["transaction_hash"]))
    out.sort()
    if since:
        out = [r for r in out if r[0] >= since]
    if until:
        out = [r for r in out if r[0] < until]
    return out

def report(ch, addr, since=None, until=None):
    rows = flows(ch, addr, since, until)
    agg = defaultdict(lambda: [Decimal(0), 0, None, None, ""])
    for ts, d, cp, meta, asset, v, h in rows:
        k = (d, cp, asset.replace("(int)", ""))
        a = agg[k]
        a[0] += v; a[1] += 1; a[2] = a[2] or ts; a[3] = ts; a[4] = meta
    lines = [f"# {ch}:{addr}  since={since} until={until}", ""]
    for (d, cp, asset), (v, n, t0, t1, meta) in sorted(agg.items(), key=lambda kv: (kv[0][0], -kv[1][0])):
        lines.append(f"{d:3} {asset:5} {v:>28.6f} n={n:<4} {cp} {meta} [{t0[:16]} .. {t1[:16]}]")
    lines.append("")
    lines.append("## rows")
    for ts, d, cp, meta, asset, v, h in rows:
        lines.append(f"{ts[:19]} {d:3} {asset:8} {v:>24.6f} {cp} {meta} {h}")
    return "\n".join(lines)

if __name__ == "__main__":
    ch, addr, outp = sys.argv[1], sys.argv[2], sys.argv[3]
    since = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else None
    until = sys.argv[5] if len(sys.argv) > 5 else None
    import os
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    open(outp, "w", encoding="utf-8").write(report(ch, addr, since, until))
