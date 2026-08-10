# bridge-optimizer

I got tired of manually checking Across, Hop, and Stargate interfaces every time I wanted to move funds between L1, Arbitrum, Optimism, and Base. This CLI tool queries live gas prices and fee APIs to find the cheapest route.

## Installation

Clone this repo and install dependencies:

```cmd
pip install -r requirements.txt
```

## Usage

Run the tool with the token, amount, source chain, and destination chain:

```cmd
python -m optimizer --token ETH --amount 0.5 --from ethereum --to arbitrum
```

Supported tokens: ETH, USDC, USDT.
Supported chains: ethereum, arbitrum, optimism, base.
