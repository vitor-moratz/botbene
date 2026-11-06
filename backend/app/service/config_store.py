"""Configuração feita pela tela (data/config.json, fora do git).

A senha da IQ fica só neste arquivo (permissão 600) e nunca volta para o painel: a API só diz
se existe uma senha salva. Sem login na tela, vale o que está no backend/.env.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.analytics.timeline import BRT
from app.market.candle import normalize_asset, valid_asset
from app.risk import MAX_GALE_LEVELS, RiskConfig
from app.strategies.intra import INTRA_NAMES

# sinais = só registra (paper) · aprovacao = você aprova cada entrada · automatico = o bot entra sozinho na demo
# automatico_veto = entra sozinho, mas o pedido aparece e você pode cancelar antes do gatilho
Mode = Literal["sinais", "aprovacao", "automatico", "automatico_veto"]
ORDER_MODES = ("aprovacao", "automatico", "automatico_veto")
# off = não roda · observe = anota e mede, sem mandar ordem · operate = pode mandar ordem, conforme o modo
StrategyState = Literal["off", "observe", "operate"]
DEFAULT_CHART_SCRIPTS = {"ldp_lines": True, "ldp_arrows": True, "wiki_pro": False}


class UserConfig(BaseModel):
    iq_email: str = ""
    iq_password: str = ""
    # Conta onde as ordens saem. REAL só muda pela rota /api/account, com a confirmação digitada
    # (a tela de Configuração não consegue trocar sem querer).
    account: Literal["PRACTICE", "REAL"] = "PRACTICE"
    mode: Mode = "sinais"
    # Estado de cada estratégia. A que não está na lista fica desligada.
    strategies: dict[str, StrategyState] = Field(default_factory=lambda: {"retracao_comando": "operate"})
    # Scripts são ajuda visual: só desenham no gráfico, nunca decidem entrada nem entram nas estatísticas.
    chart_scripts: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_CHART_SCRIPTS))
    stake: float = Field(2.0, ge=1.0, le=10_000)
    stop_win: float | None = Field(20.0, ge=0)
    stop_loss: float | None = Field(20.0, ge=0)
    max_trades: int | None = Field(30, ge=1, le=1000)
    max_consecutive_losses: int | None = Field(4, ge=1, le=100)
    martingale: bool = False  # "com análise": o gale só vale para a próxima entrada válida (e aprovada)
    gale_levels: int = Field(1, ge=1, le=MAX_GALE_LEVELS)
    # Filtros de entrada (valem para pedidos e ordens; o sinal continua sendo registrado para a estatística).
    # Payout mínimo em fração (0.80 = 80%): com payout menor, o acerto para empatar sobe (80% → 55,6%).
    min_payout: float | None = Field(0.80, ge=0.5, le=1.0)
    # Janela de operação no horário de Brasília ("HH:MM"). Vazio = o dia todo. Fim antes do início = passa da meia-noite.
    hours_start: str | None = None
    hours_end: str | None = None
    # Pares normais de binária na IQ terminam em "-op" (o "EURUSD" sem sufixo é outro instrumento).
    assets: list[str] = Field(default_factory=lambda: ["EURUSD-op"])
    timeframe: Literal[60, 120, 300] = 60

    @model_validator(mode="before")
    @classmethod
    def convert_old_file(cls, data: object) -> object:
        """config.json antigo: quem estava em `order_strategies` passa a operar; `comparison` deixa de existir."""
        if isinstance(data, dict) and "strategies" not in data and "order_strategies" in data:
            data = dict(data)
            data["strategies"] = {name: "operate" for name in data.pop("order_strategies") or [] if name in INTRA_NAMES}
        return data

    @field_validator("strategies")
    @classmethod
    def only_known_strategies(cls, v: dict[str, str]) -> dict[str, str]:
        bad = [s for s in v if s not in INTRA_NAMES]
        if bad:
            raise ValueError(f"não é uma estratégia: {', '.join(bad)}")
        return v

    @field_validator("chart_scripts")
    @classmethod
    def only_known_scripts(cls, v: dict[str, bool]) -> dict[str, bool]:
        bad = [s for s in v if s not in DEFAULT_CHART_SCRIPTS]
        if bad:
            raise ValueError(f"script desconhecido: {', '.join(bad)}")
        return DEFAULT_CHART_SCRIPTS | v

    @property
    def operating(self) -> list[str]:
        return [name for name, state in self.strategies.items() if state == "operate"]

    @property
    def running(self) -> list[str]:
        return [name for name, state in self.strategies.items() if state != "off"]

    @field_validator("hours_start", "hours_end")
    @classmethod
    def hhmm(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        parts = v.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts) or not (0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60):
            raise ValueError(f"horário inválido: {v!r} (use HH:MM, ex.: 09:00)")
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    @model_validator(mode="after")
    def hours_pair(self) -> UserConfig:
        if (self.hours_start is None) != (self.hours_end is None):
            raise ValueError("preencha o início e o fim do horário de operação (ou deixe os dois vazios)")
        if self.hours_start is not None and self.hours_start == self.hours_end:
            raise ValueError("o início e o fim do horário de operação são iguais")
        return self

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

    def entry_block(self, payout: float | None, entry_ts: float) -> str | None:
        """Motivo para NÃO mandar ordem nesta entrada (payout baixo, fora do horário), ou None."""
        if self.min_payout is not None and payout is not None and payout < self.min_payout - 1e-9:
            return f"payout de {payout * 100:.0f}% abaixo do mínimo de {self.min_payout * 100:.0f}%"
        if self.hours_start and self.hours_end:
            now = datetime.fromtimestamp(entry_ts, tz=BRT).strftime("%H:%M")
            start, end = self.hours_start, self.hours_end
            inside = start <= now < end if start < end else (now >= start or now < end)
            if not inside:
                return f"fora do horário de operação ({start}–{end})"
        return None

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
                new_email = (patch.get("iq_email") or "").strip().lower()
                if new_email and new_email != (self._cfg.iq_email or self._env_email).strip().lower():
                    raise ValueError("Digite a senha da conta nova: a senha salva é de outro e-mail.")
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
        data["strategy_names"] = list(INTRA_NAMES)  # o que a tela de Configuração oferece
        return data
