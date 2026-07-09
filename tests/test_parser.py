import pytest
from solana_copy_trader.parser import parse_transaction_logs, extract_raydium_log, extract_jupiter_event
from solana_copy_trader.types import SwapEvent, DexType

RAYDIUM_SWAP_LOGS = [
    "Program ComputeBudget111111111111111111111111111111 invoke [1]",
    "Program ComputeBudget111111111111111111111111111111 success",
    "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
    "Program log: ray_log: BAe9mAYAAAAAmc8DAAAAAACJqQQAAAAAANwNAgAAAAAA",
    "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success",
]

# Jupiter V6 route event emitted via Program data log
JUPITER_V6_LOGS = [
    "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]",
    "Program log: Instruction: Route",
    "Program data: NvZzU9rQ1H8BAAAAeTxvAAAAAABCdwAAAAAAABwVAAAAAAAA",
    "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 success",
]

# Multi-hop Jupiter route touching raydium as inner leg
JUPITER_ROUTED_RAYDIUM_LOGS = [
    "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]",
    "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [2]",
    "Program log: ray_log: BAe9mAYAAAAAmc8DAAAAAACJqQQAAAAAANwNAgAAAAAA",
    "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success",
    "Program data: NvZzU9rQ1H8BAAAAeTxvAAAAAABCdwAAAAAAABwVAAAAAAAA",
    "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 success",
]


def test_parse_raydium_swap_log():
    signature = "5wG3hMvW6eB2xP9u7qK4jLmNzV8cT1sDyXfR3aQ2bE5gH6kP8rM4tU7yW9zX1vC"
    events = parse_transaction_logs(signature, RAYDIUM_SWAP_LOGS)
    
    assert len(events) == 1
    swap = events[0]
    assert isinstance(swap, SwapEvent)
    assert swap.dex == DexType.RAYDIUM
    assert swap.signature == signature
    assert swap.amount_in > 0
    assert swap.amount_out > 0


def test_parse_jupiter_v6_swap_log():
    signature = "4tZ8jK1mNxP7vC2qR9wL5eY8uM3bF6hG4kP2rN8tU1yW5zX7vB9dE3gH5jK7mN2p"
    events = parse_transaction_logs(signature, JUPITER_V6_LOGS)
    
    assert len(events) == 1
    swap = events[0]
    assert swap.dex == DexType.JUPITER
    assert swap.signature == signature
    assert swap.amount_in > 0


def test_nested_jupiter_prefers_outer_route():
    # When jup calls raydium as a sub-step, avoid emitting duplicate swaps
    # if the top-level jup route is present
    events = parse_transaction_logs("sig_multi", JUPITER_ROUTED_RAYDIUM_LOGS)
    assert len(events) == 1
    assert events[0].dex == DexType.JUPITER


def test_ignore_unrelated_logs():
    logs = [
        "Program 11111111111111111111111111111111 invoke [1]",
        "Program 11111111111111111111111111111111 success",
    ]
    events = parse_transaction_logs("sig_test", logs)
    assert events == []


def test_corrupt_ray_log_payload():
    logs = [
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
        "Program log: ray_log: not_valid_base64!",
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success",
    ]
    events = parse_transaction_logs("sig_corrupt", logs)
    assert events == []


def test_short_ray_log_bytes():
    # Valid base64 but too short for standard struct unpack
    # print("testing truncated buffer")
    logs = [
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]",
        "Program log: ray_log: AAAA",
        "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success",
    ]
    res = extract_raydium_log(logs[1])
    assert res is None
