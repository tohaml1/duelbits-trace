"""Print explorer metadata (name, tags, contract, implementation, balance, tx count) for addresses."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
import chain

ch, outp, *addrs = sys.argv[1:]
if len(addrs) == 1 and os.path.isfile(addrs[0]):
    addrs = [l.split("#")[0].strip() for l in open(addrs[0]) if l.split("#")[0].strip()]
lines = []
for a in addrs:
    try:
        d = chain.bs_address(ch, a)
        try:
            c = chain.get_json(f"{chain.BLOCKSCOUT[ch]}/addresses/{a}/counters")
        except Exception:
            c = {}
        impl = ",".join((i.get("name") or "") + ":" + (i.get("address_hash") or i.get("address") or "") for i in (d.get("implementations") or []))
        tags = ",".join(t.get("display_name", "") for t in (d.get("public_tags") or []))
        md = d.get("metadata") or {}
        mtags = ",".join(t.get("name", "") for t in (md.get("tags") or []))
        bal = Decimal(d.get("coin_balance") or 0) / Decimal(10**18)
        lines.append(f"{a} | name={d.get('name')} | contract={d.get('is_contract')} | tags={tags} | meta={mtags} | impl={impl} | ens={d.get('ens_domain_name')} | bal={bal:.6f} | txs={c.get('transactions_count')} | creator={d.get('creator_address_hash')}")
    except Exception as e:
        lines.append(f"{a} | ERR {e}")
os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
open(outp, "w", encoding="utf-8").write("\n".join(lines))
