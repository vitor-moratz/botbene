"""Configuração lida do arquivo backend/.env (credenciais nunca vão para o banco nem para o git)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    iq_email: str = ""
    iq_password: str = ""
    iq_account: str = "PRACTICE"
    # Trava de segurança: a conta REAL só pode ser selecionada se isto for True.
    iq_allow_real: bool = False

    data_dir: Path = BACKEND_DIR.parent / "data"

    # Modo paper: payout usado quando a IQ não informar o do ativo (0.85 = 85%).
    default_payout: float = 0.85
    # Velas de histórico carregadas ao iniciar (também viram o backtest imediato no painel).
    history_candles: int = 500

    def resolved_data_dir(self) -> Path:
        path = self.data_dir if self.data_dir.is_absolute() else (BACKEND_DIR / self.data_dir)
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def db_url(self) -> str:
        return f"sqlite:///{self.resolved_data_dir() / 'botbene.sqlite'}"


def get_settings() -> Settings:
    return Settings()
