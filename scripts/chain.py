"""Thin, cached clients for the public block-explorer APIs used in this report.

No API keys. Every raw response is written to data/raw/ so the analysis can be
re-run offline and anyone can diff what the explorers returned.
"""
import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "duelbits-trace/1.0 (research)"}

BLOCKSCOUT = {
    "eth": "https://eth.blockscout.com/api/v2",
    "base": "https://base.blockscout.com/api/v2",
    "arb": "https://arbitrum.blockscout.com/api/v2",
    "op": "https://optimism.blockscout.com/api/v2",
    "gnosis": "https://gnosis.blockscout.com/api/v2",
}


def _cache_path(key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return RAW / f"{h}.json"


def get_json(url, params=None, use_cache=True, method="GET", body=None, tries=5):
    key = json.dumps([method, url, params, body], sort_keys=True)
    p = _cache_path(key)
    if use_cache and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["response"]
    for i in range(tries):
        try:
            if method == "GET":
                r = requests.get(url, params=params, headers=UA, timeout=60)
            else:
                r = requests.post(url, json=body, headers=UA, timeout=60)
            if r.status_code == 429:
                time.sleep(2 + 3 * i)
                continue
            r.raise_for_status()
            data = r.json()
            p.write_text(json.dumps({"request": json.loads(key), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "response": data}), encoding="utf-8")
            return data
        except (requests.RequestException, ValueError):
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)


# ---------- Blockscout (EVM) ----------

def bs_paged(chain, path, params=None, max_pages=200):
    """Yield every item from a paginated Blockscout v2 endpoint."""
    base = BLOCKSCOUT[chain]
    params = dict(params or {})
    for _ in range(max_pages):
        d = get_json(f"{base}{path}", params=params)
        for it in d.get("items", []):
            yield it
        nxt = d.get("next_page_params")
        if not nxt:
            return
        params = {**(params or {}), **{k: v for k, v in nxt.items() if v is not None}}


def bs_address(chain, addr):
    return get_json(f"{BLOCKSCOUT[chain]}/addresses/{addr}")


def bs_txs(chain, addr):
    return list(bs_paged(chain, f"/addresses/{addr}/transactions"))


def bs_token_transfers(chain, addr):
    return list(bs_paged(chain, f"/addresses/{addr}/token-transfers"))


def bs_internal(chain, addr):
    return list(bs_paged(chain, f"/addresses/{addr}/internal-transactions"))


def bs_tx(chain, h):
    return get_json(f"{BLOCKSCOUT[chain]}/transactions/{h}")


def bs_tx_token_transfers(chain, h):
    return list(bs_paged(chain, f"/transactions/{h}/token-transfers"))


def bs_tx_internal(chain, h):
    return list(bs_paged(chain, f"/transactions/{h}/internal-transactions"))


def bs_tx_logs(chain, h):
    return list(bs_paged(chain, f"/transactions/{h}/logs"))


# ---------- BNB Chain (JSON-RPC) ----------

BSC_RPC = "https://bsc-dataseed.bnbchain.org"


def bsc_rpc(method, params):
    d = get_json(BSC_RPC, method="POST", body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return d.get("result")


# ---------- Tron (TronGrid v1) ----------

TRONGRID = "https://api.trongrid.io"


def tron_paged(path, params=None, max_pages=100):
    url = f"{TRONGRID}{path}"
    params = dict(params or {}, limit=200)
    for _ in range(max_pages):
        d = get_json(url, params=params)
        for it in d.get("data", []):
            yield it
        fp = (d.get("meta") or {}).get("fingerprint")
        if not fp:
            return
        params = {**params, "fingerprint": fp}


def tron_account(addr):
    return get_json(f"{TRONGRID}/v1/accounts/{addr}")


def tron_txs(addr, **kw):
    return list(tron_paged(f"/v1/accounts/{addr}/transactions", kw))


def tron_trc20(addr, **kw):
    return list(tron_paged(f"/v1/accounts/{addr}/transactions/trc20", kw))


# ---------- Bitcoin (Blockstream Esplora) ----------

ESPLORA = "https://blockstream.info/api"


def btc_address(addr):
    return get_json(f"{ESPLORA}/address/{addr}")


def btc_txs(addr, max_pages=50):
    out, last = [], None
    for _ in range(max_pages):
        url = f"{ESPLORA}/address/{addr}/txs" + (f"/chain/{last}" if last else "")
        page = get_json(url)
        if not page:
            break
        out.extend(page)
        if len(page) < 25:
            break
        last = page[-1]["txid"]
    return out


def btc_tx(txid):
    return get_json(f"{ESPLORA}/tx/{txid}")
