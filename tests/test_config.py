import os
import pytest
from pathlib import Path
from solana_copy_trader.config import load_config, Config


def test_load_default_config(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[rpc]
http_url = "https://api.mainnet-beta.solana.com"
ws_url = "wss://api.mainnet-beta.solana.com"

[trading]
max_slippage_bps = 150
fixed_sol_amount = 0.05

[targets]
wallets = [
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
]
""")

    cfg = load_config(cfg_file)
    assert cfg.rpc.http_url == "https://api.mainnet-beta.solana.com"
    assert cfg.trading.max_slippage_bps == 150
    assert cfg.trading.fixed_sol_amount == 0.05
    assert len(cfg.tracked_wallets) == 2
    assert cfg.dry_run is True


def test_slippage_bounds(tmp_path: Path):
    bad_cfg = tmp_path / "bad_config.toml"
    bad_cfg.write_text("""
[rpc]
http_url = "https://api.mainnet-beta.solana.com"
ws_url = "wss://api.mainnet-beta.solana.com"

[trading]
max_slippage_bps = 6000
""")
    with pytest.raises(ValueError, match="max_slippage_bps too high"):
        load_config(bad_cfg)


def test_env_var_override_keypair(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[rpc]
http_url = "https://api.mainnet-beta.solana.com"
ws_url = "wss://api.mainnet-beta.solana.com"
""")
    
    # simulate private key passed via env instead of plain file
    monkeypatch.setenv("SOLANA_PRIVATE_KEY", "[1,2,3,4,5]")
    cfg = load_config(cfg_file)
    assert cfg.private_key_raw == "[1,2,3,4,5]"


def test_strip_whitespace_in_target_wallets(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("""
[rpc]
http_url = "https://api.mainnet-beta.solana.com"
ws_url = "wss://api.mainnet-beta.solana.com"

[targets]
wallets = ["  675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8  "]
""")
    cfg = load_config(cfg_file)
    assert cfg.tracked_wallets[0] == "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
