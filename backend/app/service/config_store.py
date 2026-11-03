"""Configuração feita pela tela (data/config.json, fora do git).

A senha da IQ fica só neste arquivo (permissão 600) e nunca volta para o painel: a API só diz
se existe uma senha salva. Sem login na tela, vale o que está no backend/.env.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.market.candle import normalize_asset, valid_asset
from app.risk import MAX_GALE_LEVELS, RiskConfig
from app.strategies.intra import INTRA_NAMES

# sinais = só registra (paper) · aprovacao = você aprova cada entrada · automatico = o bot entra sozinho na demo
# automatico_veto = entra sozinho, mas o pedido aparece e você pode cancelar antes do gatilho
Mode = Literal["sinais", "aprovacao", "automatico", "automatico_veto"]
ORDER_MODES = ("aprovacao", "automatico", "automatico_veto")


class UserConfig(BaseModel):
    iq_email: str = ""
    iq_password: str = ""
    # Conta onde as ordens saem. REAL só muda pela rota /api/account, com a confirmação digitada
    # (a tela de Configuração não consegue trocar sem querer).
    account: Literal["PRACTICE", "REAL"] = "PRACTICE"
    mode: Mode = "sinais"
    order_strategies: list[str] = Field(default_factory=lambda: ["retracao_comando"])
    # Scripts de comparação (LDP v1.3, regra das linhas, WIKI PRO, marcações): só registram, nunca mandam ordem.
    # Desligados, o bot avalia só as estratégias acima e as telas ficam só com elas.
    comparison: bool = False
    stake: float = Field(2.0, ge=1.0, le=10_000)
    stop_win: float | None = Field(20.0, ge=0)
    stop_loss: float | None = Field(20.0, ge=0)
    max_trades: int | None = Field(30, ge=1, le=1000)
    max_consecutive_losses: int | None = Field(4, ge=1, le=100)
    martingale: bool = False  # "com análise": o gale só vale para a próxima entrada válida (e aprovada)
    gale_levels: int = Field(1, ge=1, le=MAX_GALE_LEVELS)
    # Pares normais de binária na IQ terminam em "-op" (o "EURUSD" sem sufixo é outro instrumento).
    assets: list[str] = Field(default_factory=lambda: ["EURUSD-op"])
    timeframe: Literal[60, 120, 300] = 60

    @field_validator("order_strategies")
    @classmethod
    def only_intra(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in INTRA_NAMES]
        if bad:
            raise ValueError(f"estratégia sem gatilho dentro da vela: {', '.join(bad)}")
        return v

    @field_validator("assets")
    @classmethod
    def norm_assets(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for a in v:
            a = normalize_asset(a)
            if not valid_asset(a):
                raise ValueError(f"ativo inválido: {a!r}")
            if a not in out:
                out.append(a)
        if not out:
            raise ValueError("escolha pelo menos um ativo")
        if len(out) > 8:
            raise ValueError("no máximo 8 ativos ao mesmo tempo")
        return out

    def risk(self) -> RiskConfig:
        return RiskConfig(stake=self.stake, stop_win=self.stop_win or None, stop_loss=self.stop_loss or None,
                          max_trades=self.max_trades, max_consecutive_losses=self.max_consecutive_losses,
                          martingale=self.martingale, gale_levels=self.gale_levels)


class ConfigStore:
    def __init__(self, path: Path, env_email: str = "", env_password: str = "") -> None:
        self.path = path
        self._env_email, self._env_password = env_email, env_password
        self._lock = threading.Lock()
        self._cfg = self._read()

    def _read(self) -> UserConfig:
        if self.path.exists():
            try:
                return UserConfig.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass  # arquivo estragado: volta ao padrão (a senha do .env continua valendo)
        return UserConfig()

    def get(self) -> UserConfig:
        with self._lock:
            return self._cfg.model_copy(deep=True)

    def update(self, patch: dict) -> UserConfig:
        with self._lock:
            data = self._cfg.model_dump()
            if not patch.get("iq_password"):
                patch.pop("iq_password", None)  # campo vazio = manter a senha salva
            data.update(patch)
            cfg = UserConfig.model_validate(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)
            self._cfg = cfg
            return cfg.model_copy(deep=True)

    def credentials(self) -> tuple[str, str]:
        cfg = self.get()
        if cfg.iq_email and cfg.iq_password:
            return cfg.iq_email, cfg.iq_password
        return self._env_email, self._env_password

    def public(self) -> dict:
        cfg = self.get()
        data = cfg.model_dump(exclude={"iq_password"})
        if cfg.iq_email and cfg.iq_password:
            source = "tela"
        elif self._env_email and self._env_password:
            source = "arquivo .env"
        else:
            source = None
        data["iq_email"] = cfg.iq_email or self._env_email
        data["has_password"] = source is not None
        data["credentials_source"] = source
        return data
