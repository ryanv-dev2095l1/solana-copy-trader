import logging
from typing import Any, Dict, List, Optional
from solana_copy_trader.types import SwapEvent, DexType

logger = logging.getLogger(__name__)

JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
RAYDIUM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaWDAePqLsEHf"
RAYDIUM_CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
PUMP_FUN = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WSOL_MINT = "So11111111111111111111111111111111111111112"

KNOWN_PROGRAMS = {
    JUPITER_V6: DexType.JUPITER,
    RAYDIUM_V4: DexType.RAYDIUM,
    RAYDIUM_CLMM: DexType.RAYDIUM,
    RAYDIUM_CPMM: DexType.RAYDIUM,
    PUMP_FUN: DexType.PUMPFUN,
}


def identify_dex(account_keys: List[str], log_messages: List[str]) -> Optional[DexType]:
    for key in account_keys:
        if key in KNOWN_PROGRAMS:
            return KNOWN_PROGRAMS[key]

    # Fallback to program log inspection if account list was truncated or sanitized
    for msg in log_messages:
        if JUPITER_V6 in msg:
            return DexType.JUPITER
        if any(p in msg for p in (RAYDIUM_V4, RAYDIUM_CLMM, RAYDIUM_CPMM)):
            return DexType.RAYDIUM
        if PUMP_FUN in msg:
            return DexType.PUMPFUN
    return None


def _extract_amount(token_amount_obj: Dict[str, Any]) -> Optional[float]:
    ui_val = token_amount_obj.get("uiAmount")
    if ui_val is not None:
        return float(ui_val)
    # Triton / Helius sometimes returns uiAmount as null for large u64, fall back to string/decimals
    raw_str = token_amount_obj.get("amount")
    decimals = token_amount_obj.get("decimals")
    if raw_str is not None and decimals is not None:
        try:
            return int(raw_str) / (10 ** int(decimals))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def extract_sol_diff(wallet: str, account_keys: List[str], meta: Dict[str, Any]) -> float:
    try:
        idx = account_keys.index(wallet)
    except ValueError:
        return 0.0

    pre_lamports = meta.get("preBalances", [])
    post_lamports = meta.get("postBalances", [])
    if idx < len(pre_lamports) and idx < len(post_lamports):
        diff_lamports = post_lamports[idx] - pre_lamports[idx]
        # Account for tx fee if target wallet was the fee payer
        if idx == 0:
            fee = meta.get("fee", 0)
            diff_lamports += fee
        return diff_lamports / 1e9
    return 0.0


def parse_token_balance_diffs(
    wallet: str,
    pre_balances: List[Dict[str, Any]],
    post_balances: List[Dict[str, Any]],
) -> Dict[str, float]:
    balances: Dict[str, float] = {}

    # Pre balances (subtract)
    for entry in pre_balances:
        if entry.get("owner") != wallet:
            continue
        mint = entry.get("mint")
        amount = _extract_amount(entry.get("uiTokenAmount", {}))
        if mint and amount is not None:
            balances[mint] = balances.get(mint, 0.0) - amount

    # Post balances (add)
    for entry in post_balances:
        if entry.get("owner") != wallet:
            continue
        mint = entry.get("mint")
        amount = _extract_amount(entry.get("uiTokenAmount", {}))
        if mint and amount is not None:
            balances[mint] = balances.get(mint, 0.0) + amount

    return {mint: diff for mint, diff in balances.items() if abs(diff) > 1e-9}


def parse_swap_tx(signature: str, target_wallet: str, tx_data: Dict[str, Any]) -> Optional[SwapEvent]:
    """Extract swap details for target_wallet from full parsed transaction json."""
    meta = tx_data.get("meta")
    if not meta or meta.get("err") is not None:
        return None

    transaction = tx_data.get("transaction", {})
    message = transaction.get("message", {})

    # Account keys can be list of strings or list of dicts depending on jsonParsed vs json encoding
    raw_keys = message.get("accountKeys", [])
    account_keys = []
    for k in raw_keys:
        if isinstance(k, dict):
            account_keys.append(k.get("pubkey", ""))
        else:
            account_keys.append(str(k))

    log_messages = meta.get("logMessages", [])
    dex = identify_dex(account_keys, log_messages)
    if not dex:
        return None

    pre_token_balances = meta.get("preTokenBalances", [])
    post_token_balances = meta.get("postTokenBalances", [])

    diffs = parse_token_balance_diffs(target_wallet, pre_token_balances, post_token_balances)
    sol_diff = extract_sol_diff(target_wallet, account_keys, meta)

    # If WSOL isn't in token diffs but native SOL changed significantly, record it as WSOL
    if abs(sol_diff) > 0.0001 and WSOL_MINT not in diffs:
        diffs[WSOL_MINT] = sol_diff

    if not diffs:
        return None

    # # print(f"debug diffs for {signature}: {diffs}")

    in_mint = None
    out_mint = None
    in_amount = 0.0
    out_amount = 0.0

    for mint, diff in diffs.items():
        if diff < 0:
            in_mint = mint
            in_amount = abs(diff)
        elif diff > 0:
            out_mint = mint
            out_amount = diff

    # In multi-hop routing we occasionally see intermediary token dust, TODO: take highest volume leg
    if not in_mint or not out_mint:
        return None

    return SwapEvent(
        signature=signature,
        wallet=target_wallet,
        dex=dex,
        in_mint=in_mint,
        in_amount=in_amount,
        out_mint=out_mint,
        out_amount=out_amount,
        slot=tx_data.get("slot", 0),
        block_time=tx_data.get("blockTime"),
    )
