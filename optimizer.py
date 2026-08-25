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

def calc_across_fee(amount: float, dest_chain: str, gas_price_wei: int, eth_price: float) -> float:
    # Across uses a relayer gas fee + percentage fee (~0.04%)
    # Destination execution cost is around 85,000 gas
    dest_gas_limit = 85000
    dest_gas_cost_eth = (dest_gas_limit * gas_price_wei) / 1e18
    dest_gas_cost_usd = dest_gas_cost_eth * eth_price
    
    percent_fee_usd = amount * 0.0004 * eth_price
    return dest_gas_cost_usd + percent_fee_usd

def calc_hop_fee(amount: float, dest_chain: str, gas_price_wei: int, eth_price: float) -> float:
    # Hop has a minimum fee and percentage fee (~0.04%)
    # Destination execution cost is around 100,000 gas
    dest_gas_limit = 100000
    dest_gas_cost_eth = (dest_gas_limit * gas_price_wei) / 1e18
    dest_gas_cost_usd = dest_gas_cost_eth * eth_price
    
    min_fee_usd = 0.0005 * eth_price
    percent_fee_usd = amount * 0.0004 * eth_price
    
    return dest_gas_cost_usd + max(min_fee_usd, percent_fee_usd)

def main():
    parser = argparse.ArgumentParser(
        description="Calculate cheapest bridging routes between L1 and L2s.",
        epilog="Example: optimizer.py --amount 0.5 --source ethereum --dest arbitrum"
    )
    parser.add_argument("--amount", type=float, required=True, help="Amount of ETH to bridge")
    parser.add_argument("--source", choices=RPCS.keys(), required=True, help="Source chain")
    parser.add_argument("--dest", choices=RPCS.keys(), required=True, help="Destination chain")
    
    args = parser.parse_args()
    
    if args.source == args.dest:
        sys.exit("Source and destination chains must be different.")

    # Fetch live gas prices
    try:
        dest_gas_wei = get_gas_price(args.dest)
    except Exception as e:
        print(f"Error querying RPC for {args.dest}: {e}", file=sys.stderr)
        sys.exit(1)

    # Fallback to fixed ETH price for now
    eth_price = 3200.0
    
    across_cost = calc_across_fee(args.amount, args.dest, dest_gas_wei, eth_price)
    hop_cost = calc_hop_fee(args.amount, args.dest, dest_gas_wei, eth_price)
    
    print(f"Bridging {args.amount} ETH from {args.source.upper()} to {args.dest.upper()}")
    print(f"Across estimated cost: ${across_cost:.2f}")
    print(f"Hop estimated cost: ${hop_cost:.2f}")

if __name__ == "__main__":
    main()
