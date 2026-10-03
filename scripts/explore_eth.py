"""Exploration pass: dump a compact ledger for an EVM address (txs, internal, tokens)."""
import sys
from decimal import Decimal

import chain

def name(a):
    if not a:
        return ""
    n = a.get("name") or ""
    tags = ",".join(t.get("display_name", "") for t in (a.get("public_tags") or []))
    return f"{a['hash']}{' ['+n+']' if n else ''}{' {'+tags+'}' if tags else ''}{' (contract)' if a.get('is_contract') else ''}"

def ledger(ch, addr, since=None):
    rows = []
    for t in chain.bs_txs(ch, addr):
        rows.append((t["timestamp"], "tx", t["hash"], name(t["from"]), name(t.get("to")), Decimal(t["value"]) / Decimal(10**18), "NATIVE", t.get("method") or "", t.get("status")))
    for t in chain.bs_internal(ch, addr):
        if Decimal(t["value"]) == 0:
            continue
        rows.append((t["timestamp"], "int", t["transaction_hash"], name(t["from"]), name(t.get("to")), Decimal(t["value"]) / Decimal(10**18), "NATIVE", t.get("type") or "", "ok" if t.get("success") else "fail"))
    for t in chain.bs_token_transfers(ch, addr):
        tok = t["token"]
        dec = int(tok.get("decimals") or 0)
        val = t["total"].get("value") if t.get("total") else None
        amt = Decimal(val) / Decimal(10**dec) if val is not None else Decimal(0)
        rows.append((t["timestamp"], "tok", t["transaction_hash"], name(t["from"]), name(t["to"]), amt, f"{tok.get('symbol')}:{tok['address_hash'] if 'address_hash' in tok else tok.get('address')}", t.get("method") or "", t.get("type")))
    rows.sort()
    if since:
        rows = [r for r in rows if r[0] >= since]
    return rows

if __name__ == "__main__":
    ch, addr, out = sys.argv[1], sys.argv[2], sys.argv[3]
    since = sys.argv[4] if len(sys.argv) > 4 else None
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in ledger(ch, addr, since):
            f.write(" | ".join(str(x) for x in r) + "\n")
