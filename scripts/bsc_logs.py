"""BNB Chain via raw JSON-RPC: ERC-20 Transfer logs to/from an address in a time window.

No keyless BscScan-style indexer exists, so we binary-search block numbers by
timestamp and page eth_getLogs in fixed block windows.
"""
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
import chain

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
KNOWN = {
    "0x55d398326f99059ff775485246999027b3197955": ("USDT", 18),
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("USDC", 18),
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": ("ETH(BEP20)", 18),
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": ("WBNB", 18),
    "0xe9e7cea3dedca5984780bafc599bd69add087d56": ("BUSD", 18),
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": ("BTCB", 18),
}


def block_ts(n):
    b = chain.bsc_rpc("eth_getBlockByNumber", [hex(n), False])
    return int(b["timestamp"], 16)


def block_at(ts):
    hi = int(chain.get_json(chain.BSC_RPC, method="POST", body={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}, use_cache=False)["result"], 16)
    lo = hi - 3_000_000
    while lo < hi:
        mid = (lo + hi) // 2
        if block_ts(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def pad(a):
    return "0x" + "0" * 24 + a.lower()[2:]


def logs(addr, t0, t1, step=1000):
    b0, b1 = block_at(t0), block_at(t1)
    out = []
    for side in ("from", "to"):
        topics = [TRANSFER, pad(addr), None] if side == "from" else [TRANSFER, None, pad(addr)]
        for s in range(b0, b1 + 1, step):
            res = chain.bsc_rpc("eth_getLogs", [{"fromBlock": hex(s), "toBlock": hex(min(s + step - 1, b1)), "topics": topics}])
            for l in res or []:
                tok = l["address"].lower()
                sym, dec = KNOWN.get(tok, (tok, 18))
                v = Decimal(int(l["data"], 16)) / Decimal(10**dec) if l["data"] != "0x" else Decimal(0)
                out.append({
                    "block": int(l["blockNumber"], 16), "tx": l["transactionHash"], "token": sym, "token_addr": tok,
                    "from": "0x" + l["topics"][1][-40:], "to": "0x" + l["topics"][2][-40:], "amount": str(v),
                })
    return b0, b1, out


if __name__ == "__main__":
    addr, outp, start, end = sys.argv[1:5]
    t0 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    t1 = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())
    b0, b1, out = logs(addr, t0, t1)
    for o in out:
        o["ts"] = datetime.fromtimestamp(block_ts(o["block"]), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    json.dump({"address": addr, "blocks": [b0, b1], "transfers": sorted(out, key=lambda x: x["block"])}, open(outp, "w"), indent=1)
    print(len(out))
