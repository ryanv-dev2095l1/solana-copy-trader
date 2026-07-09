import pytest
import asyncio
from solana_copy_trader.executor import OrderExecutor, SizingMode, ExecutionResult
from solana_copy_trader.config import TraderConfig
from solana_copy_trader.types import SwapEvent, DexType


@pytest.fixture
def default_cfg():
    return TraderConfig(
        target_wallets=["7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"],
        sizing_mode=SizingMode.FIXED_SOL,
        fixed_sol_amount=0.2,
        copy_ratio=0.5,
        max_sol_per_trade=1.0,
        max_slippage_bps=150,
        dry_run=True,
        min_sol_reserve=0.05,
    )


def test_fixed_sol_sizing(default_cfg):
    executor = OrderExecutor(default_cfg)
    event = SwapEvent(
        dex=DexType.RAYDIUM,
        signature="test_sig_1",
        signer="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=5_000_000_000,  # 5 SOL
        amount_out=1_000_000_000,
    )
    size = executor.calculate_order_size(event, current_sol_balance=2.0)
    assert size == 200_000_000


def test_proportional_sizing(default_cfg):
    default_cfg.sizing_mode = SizingMode.PERCENTAGE
    executor = OrderExecutor(default_cfg)
    
    event = SwapEvent(
        dex=DexType.RAYDIUM,
        signature="test_sig_2",
        signer="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=2_000_000_000,  # 2 SOL
        amount_out=400_000_000,
    )
    size = executor.calculate_order_size(event, current_sol_balance=5.0)
    assert size == 1_000_000_000


def test_max_sol_cap_applied(default_cfg):
    default_cfg.sizing_mode = SizingMode.PERCENTAGE
    default_cfg.copy_ratio = 1.0
    default_cfg.max_sol_per_trade = 0.5
    executor = OrderExecutor(default_cfg)
    
    event = SwapEvent(
        dex=DexType.RAYDIUM,
        signature="test_sig_3",
        signer="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=10_000_000_000,  # 10 SOL
        amount_out=2_000_000_000,
    )
    size = executor.calculate_order_size(event, current_sol_balance=5.0)
    assert size == 500_000_000


def test_insufficient_balance_for_reserve(default_cfg):
    # balance is 0.1 SOL, order wants 0.2 SOL, reserve is 0.05 SOL
    executor = OrderExecutor(default_cfg)
    event = SwapEvent(
        dex=DexType.RAYDIUM,
        signature="test_sig_4",
        signer="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=1_000_000_000,
        amount_out=100_000_000,
    )
    size = executor.calculate_order_size(event, current_sol_balance=0.10)
    # Remaining after reserve: 0.05 SOL
    assert size == 50_000_000


@pytest.mark.asyncio
async def test_dry_run_execution(default_cfg):
    executor = OrderExecutor(default_cfg)
    event = SwapEvent(
        dex=DexType.JUPITER,
        signature="test_sig_dry",
        signer="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        amount_in=1_000_000_000,
        amount_out=50_000_000,
    )
    
    result = await executor.execute(event, current_sol_balance=2.0)
    assert result.success is True
    assert result.dry_run is True
    assert result.simulated_tx_sig.startswith("sim_")
    assert result.amount_in == 200_000_000
