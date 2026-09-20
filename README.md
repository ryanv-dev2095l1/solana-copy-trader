# solana-copy-trader

Personal daemon I use to track a handful of target wallets and replicate their Raydium and Jupiter swaps with fixed position sizing and strict slippage checks.

Built because most commercial bots are closed source, full of telemetry, or rely on paid telegram setups that choke during network congestion. This connects straight to your RPC/WSS node, parses transaction logs as they arrive, and fires execution via local keypair.

## Requirements

- Python 3.11+
- A reliable Solana RPC endpoint with WebSocket support (Triton, Helius, or private node recommended)
- Funded keypair file for execution

## Setup

```bash
git clone https://github.com/username/solana-copy-trader.git
cd solana-copy-trader
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy the example environment configuration:

```bash
cp .env.example .env
# Edit .env with your RPC urls and target addresses
```

## Usage

Run the listener in dry-run mode first to make sure log parsing works with your RPC:

```bash
solana-copy-trader run --dry-run
```

Track a specific wallet live:

```bash
solana-copy-trader track <WALLET_PUBKEY> --max-sol 0.5 --slippage 1.5
```

Inspect local trade history recorded in sqlite:

```bash
solana-copy-trader history --limit 20
```

## License

MIT

<!-- updated: 2026-09-20 -->
