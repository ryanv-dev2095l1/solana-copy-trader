import os
from pathlib import Path
from typing import List, Optional
import base58
from solders.keypair import Keypair
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Runtime configuration parsed from env variables or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RPC endpoints
    rpc_http_url: str = Field(..., alias="RPC_HTTP_URL")
    rpc_ws_url: str = Field(..., alias="RPC_WS_URL")
    backup_http_url: Optional[str] = Field(default=None, alias="BACKUP_HTTP_URL")

    # Signer credentials (can be raw base58 string or path to id.json)
    payer_private_key: str = Field(..., alias="PAYER_PRIVATE_KEY")

    # Target wallets
    tracked_wallets: List[str] = Field(default_factory=list, alias="TRACKED_WALLETS")

    # Copy settings
    fixed_buy_amount_sol: float = Field(default=0.05, alias="FIXED_BUY_AMOUNT_SOL")
    max_buy_amount_sol: float = Field(default=0.5, alias="MAX_BUY_AMOUNT_SOL")
    copy_sell_ratio: float = Field(default=1.0, alias="COPY_SELL_RATIO")
    slippage_bps: int = Field(default=250, alias="SLIPPAGE_BPS")
    
    # Compute budget & priority fees
    compute_unit_price_micro_lamports: int = Field(default=100_000, alias="PRIORITY_FEE_MICRO_LAMPORTS")
    compute_unit_limit: int = Field(default=250_000, alias="COMPUTE_UNIT_LIMIT")
    
    # Operation modes
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    db_path: Path = Field(default=Path("data/trades.db"), alias="DB_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("tracked_wallets", mode="before")
    @classmethod
    def parse_wallets(cls, v):
        if isinstance(v, str):
            return [w.strip() for w in v.split(",") if w.strip()]
        return v

    def get_keypair(self) -> Keypair:
        # check if it's a path on disk first
        val = self.payer_private_key.strip()
        if os.path.exists(val):
            with open(val, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content.startswith("[") and content.endswith("]"):
                import json
                raw = bytes(json.loads(content))
                return Keypair.from_bytes(raw)
            return Keypair.from_base58_string(content)
        
        # assume raw base58 or byte list
        if val.startswith("["):
            import json
            return Keypair.from_bytes(bytes(json.loads(val)))
        
        # print(f"debug: loading keypair from base58 len={len(val)}")
        return Keypair.from_base58_string(val)
