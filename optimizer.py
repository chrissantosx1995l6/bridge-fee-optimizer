import argparse
import sys
import httpx

# Standard public RPCs for gas price queries
RPCS = {
    "ethereum": "https://cloudflare-eth.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io"
}

def get_gas_price(chain: str) -> int:
    url = RPCS.get(chain)
    if not url:
        raise ValueError(f"Unknown chain: {chain}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_gasPrice",
        "params": [],
        "id": 1
    }
    r = httpx.post(url, json=payload, timeout=5.0)
    r.raise_for_status()
    result = r.json()
    return int(result["result"], 16)

