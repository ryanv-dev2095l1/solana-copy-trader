from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DexProtocol(str, Enum):
    RAYDIUM_V4 = "raydium_v4"
    RAYDIUM_CLMM = "raydium_clmm"
    RAYDIUM_CPMM = "raydium_cpmm"
    JUPITER_V6 = "jupiter_v6"
    PUMP_FUN = "pump_fun"
    UNKNOWN = "unknown"


class SwapSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


# SOL native mint address shorthand
NATIVE_SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = NATIVE_SOL_MINT


@dataclass(slots=True)
class RawSwapEvent:
    """Normalized swap record extracted from parsed transaction logs."""
    signature: str
    slot: int
    target_wallet: str
    protocol: DexProtocol
    side: SwapSide
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    timestamp: float
    # amm pool keys if extracted directly from inner ix
    pool_id: Optional[str] = None


@dataclass(slots=True)
class TradeOrder:
    source_sig: str
    target_wallet: str
    protocol: DexProtocol
    side: SwapSide
    input_mint: str
    output_mint: str
    amount_in_lamports: int
    min_amount_out: int
    slippage_bps: int
    priority_micro_lamports: int = 50_000
    pool_id: Optional[str] = None
    # TODO: parse exact tick arrays for clmm price impact calculation


@dataclass(slots=True)
class ExecutionResult:
    source_sig: str
    tx_hash: Optional[str]
    success: bool
    error_msg: Optional[str] = None
    latency_ms: float = 0.0
    logs: list[str] = field(default_factory=list)
