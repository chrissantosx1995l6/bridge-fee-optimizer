import argparse
import sys
from pathlib import Path
import httpx

# Fallback gas prices in gwei if public RPCs are temporarily unresponsive
FALLBACK_GAS_GWEI = {
    "ethereum": 35.0,
    "arbitrum": 0.1,
    "optimism": 0.01,
    "base": 0.01
}

RPCS = {
    "ethereum": "https://cloudflare-eth.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "base": "https://mainnet.base.org"
}

# Approximate gas limits for finalizing bridge transfers on destination chains
GAS_LIMITS = {
    "across": {"ETH": 85000, "USDC": 110000},
    "hop": {"ETH": 95000, "USDC": 125000},
    "stargate": {"ETH": 150000, "USDC": 140000} 
}

def get_gas_price(chain: str) -> int:
    """Queries the live gas price in wei from public RPC nodes."""
    url = RPCS.get(chain)
    if not url:
        raise ValueError(f"Unknown chain: {chain}")
    
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_gasPrice",
        "params": [],
        "id": 1
    }
    try:
        r = httpx.post(url, json=payload, timeout=4.0)
        r.raise_for_status()
        result = r.json()
        return int(result["result"], 16)
    except (httpx.HTTPError, KeyError, ValueError):
        # Graceful degradation using historical averages
        gwei = FALLBACK_GAS_GWEI[chain]
        return int(gwei * 1e9)

def get_eth_price() -> float:
    # Pull from DeFiLlama or Coingecko to convert gas calculations accurately
    try:
        r = httpx.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd", timeout=3.0)
        r.raise_for_status()
        return float(r.json()["ethereum"]["usd"])
    except Exception:
        # Fallback if rate-limited or offline
        return 3400.0

def calc_across(amount: float, token: str, dest_chain: str, gas_price_wei: int, eth_price: float) -> float:
    # Across fee: dest execution gas + percentage fee (typically 0.04% for ETH, 0.06% for USDC)
    limit = GAS_LIMITS["across"][token]
    dest_gas_cost_eth = (limit * gas_price_wei) / 1e18
    dest_gas_cost_usd = dest_gas_cost_eth * eth_price
    
    rate = 0.0004 if token == "ETH" else 0.0006
    pct_fee_val = amount * rate
    pct_fee_usd = pct_fee_val * eth_price if token == "ETH" else pct_fee_val
    
    return dest_gas_cost_usd + pct_fee_usd

def calc_hop(amount: float, token: str, dest_chain: str, gas_price_wei: int, eth_price: float) -> float:
    # Hop protocol fee: dest gas + max of (min flat fee, 0.04% rate)
    # FIXME: Optimism L1 fee (scalar/overhead) isn't fully accounted for here, only L2 execution gas
    limit = GAS_LIMITS["hop"][token]
    dest_gas_cost_eth = (limit * gas_price_wei) / 1e18
    dest_gas_cost_usd = dest_gas_cost_eth * eth_price
    
    if token == "ETH":
        min_fee_usd = 0.0004 * eth_price
        pct_fee_usd = amount * 0.0004 * eth_price
    else:
        min_fee_usd = 1.0
        pct_fee_usd = amount * 0.0005
        
    return dest_gas_cost_usd + max(min_fee_usd, pct_fee_usd)

def calc_stargate(amount: float, token: str, dest_chain: str, gas_price_wei: int, eth_price: float) -> float:
    # Stargate V2 charging a standard 0.06% liquidity pool fee + destination message execution gas
    # TODO: Stargate V2 has different pool rates for base, check if we need to query their on-chain fee estimator
    if token == "ETH" and dest_chain == "base":
        # Stargate ETH bridging is limited/unsupported on some routes
        return float("inf")
        
    limit = GAS_LIMITS["stargate"][token]
    dest_gas_cost_eth = (limit * gas_price_wei) / 1e18
    dest_gas_cost_usd = dest_gas_cost_eth * eth_price
    
    rate = 0.0006
    pct_fee_val = amount * rate
    pct_fee_usd = pct_fee_val * eth_price if token == "ETH" else pct_fee_val
    
    return dest_gas_cost_usd + pct_fee_usd

def main():
    parser = argparse.ArgumentParser(
        description="Finds the cheapest route for bridging tokens between L1 and popular L2s.",
        epilog="Example: python optimizer.py --amount 1.5 --token ETH --source ethereum --dest arbitrum"
    )
    parser.add_argument("--amount", type=float, required=True, help="Amount of token to bridge")
    parser.add_argument("--token", choices=["ETH", "USDC"], default="ETH", help="Token to bridge")
    parser.add_argument("--source", choices=RPCS.keys(), required=True, help="Source chain")
    parser.add_argument("--dest", choices=RPCS.keys(), required=True, help="Destination chain")
    
    args = parser.parse_args()
    
    if args.source == args.dest:
        sys.exit("Error: Source and destination chains must be different.")
        
    # Retrieve live network gas prices and ETH/USD conversion rates
    eth_price = get_eth_price()
    dest_gas_price = get_gas_price(args.dest)
    
    # print(f"DEBUG: {args.dest} gas price: {dest_gas_price / 1e9:.3f} Gwei")
    
    routes = {}
    
    # Calculate for each bridge option
    routes["Across"] = calc_across(args.amount, args.token, args.dest, dest_gas_price, eth_price)
    routes["Hop"] = calc_hop(args.amount, args.token, args.dest, dest_gas_price, eth_price)
    routes["Stargate"] = calc_stargate(args.amount, args.token, args.dest, dest_gas_price, eth_price)
    
    # Sort by cheapest
    valid_routes = {k: v for k, v in routes.items() if v != float("inf")}
    sorted_routes = sorted(valid_routes.items(), key=lambda x: x[1])
    
    if not sorted_routes:
        print("No valid routing options found.", file=sys.stderr)
        sys.exit(1)
        
    print(f"\nRoute overview: {args.amount} {args.token} from {args.source.upper()} to {args.dest.upper()}")
    print(f"Current ETH valuation: ${eth_price:,.2f} USD\n")
    print(f"{'Bridge':<12} | {'Estimated Fee (USD)':<20}")
    print("-" * 37)
    
    for name, fee in sorted_routes:
        print(f"{name:<12} | ${fee:<19.2f}")
        
    cheapest_name, cheapest_fee = sorted_routes[0]
    print(f"\nRecommended option: {cheapest_name} (saves ${sorted_routes[-1][1] - cheapest_fee:.2f} over worst option)")

if __name__ == "__main__":
    main()
