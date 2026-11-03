"""Mapa de marcações (níveis) com papel de suporte ou resistência.

Regras da apostila aplicadas aqui:
- O papel é dado pela posição: marcação abaixo do preço é suporte, acima é resistência.
- Rompimento só vale com o CORPO: a vela precisa fechar além do nível (pág. 115).
  Pavio que passa e volta é defesa, não rompimento (pág. 148).
- Nível rompido troca de papel: "a demanda de venda rompida vira demanda de compra" (pág. 95).
  Rompido pela segunda vez, o nível perde a validade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.ldp.candles import CandleInfo
from app.ldp.config import LdpConfig
from app.ldp.structures import Structure


class Role(str, Enum):
    SUPPORT = "suporte"
    RESISTANCE = "resistencia"

    def opposite(self) -> Role:
        return Role.RESISTANCE if self is Role.SUPPORT else Role.SUPPORT


@dataclass(slots=True)
class Level:
    id: int
    price: float
    role: Role
    strength: int
    sources: list[str] = field(default_factory=list)
    created_index: int = 0
    created_ts: int = 0
    last_index: int = 0
    flipped: bool = False
    touches: int = 0
    active: bool = True
    broken_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "price": self.price,
            "role": self.role.value,
            "strength": self.strength,
            "sources": list(self.sources),
            "created_index": self.created_index,
            "created_ts": self.created_ts,
            "flipped": self.flipped,
            "touches": self.touches,
            "active": self.active,
        }


@dataclass(frozen=True, slots=True)
class LevelChange:
    level_id: int
    change: str  # "defendido" | "rompido_invertido" | "rompido_desativado" | "expirado" | "descartado"
    index: int


@dataclass(frozen=True, slots=True)
class Zone:
    """Onde o preço está entre as marcações: suporte mais próximo abaixo e resistência mais próxima acima."""

    price: float
    support: Level | None
    resistance: Level | None

    @property
    def room_up(self) -> float | None:
        return None if self.resistance is None else self.resistance.price - self.price

    @property
    def room_down(self) -> float | None:
        return None if self.support is None else self.price - self.support.price


class LevelMap:
    def __init__(self, cfg: LdpConfig) -> None:
        self.cfg = cfg
        self._levels: list[Level] = []
        self._next_id = 1

    def active(self, role: Role | None = None) -> list[Level]:
        return [lv for lv in self._levels if lv.active and (role is None or lv.role is role)]

    def apply_candle(self, info: CandleInfo) -> list[LevelChange]:
        """Aplica uma vela fechada aos níveis já existentes (antes de criar os níveis dela)."""
        c = info.candle
        changes: list[LevelChange] = []
        for lv in self.active():
            if lv.created_index >= info.index:
                continue
            if lv.role is Role.SUPPORT:
                broken, touched = c.close < lv.price, c.low <= lv.price
            else:
                broken, touched = c.close > lv.price, c.high >= lv.price
            if broken:
                if lv.flipped:
                    lv.active = False
                    changes.append(LevelChange(lv.id, "rompido_desativado", info.index))
                else:
                    lv.role = lv.role.opposite()
                    lv.flipped = True
                    lv.broken_index = info.index
                    changes.append(LevelChange(lv.id, "rompido_invertido", info.index))
            elif touched:
                lv.touches += 1
                changes.append(LevelChange(lv.id, "defendido", info.index))
        return changes

    def add_structure(self, structure: Structure, info: CandleInfo, atr: float | None) -> list[Level]:
        """Cria (ou reforça) os níveis das marcações de uma estrutura confirmada na vela `info`."""
        close = info.candle.close
        tol = self.cfg.merge_tol_atr * atr if atr else 0.0
        created: list[Level] = []
        for mark in structure.marks:
            if mark.price < close:
                role = Role.SUPPORT
            elif mark.price > close:
                role = Role.RESISTANCE
            else:
                bias = structure.direction or info.direction
                role = Role.SUPPORT if bias >= 0 else Role.RESISTANCE
            source = f"{structure.name}:{mark.kind}"
            existing = self._find_near(mark.price, role, tol)
            if existing is not None:
                existing.strength = max(existing.strength, mark.strength)
                if source not in existing.sources:
                    existing.sources.append(source)
                existing.last_index = info.index
                continue
            level = Level(
                id=self._next_id,
                price=mark.price,
                role=role,
                strength=mark.strength,
                sources=[source],
                created_index=info.index,
                created_ts=info.candle.ts,
                last_index=info.index,
            )
            self._next_id += 1
            self._levels.append(level)
            created.append(level)
        return created

    def expire(self, index: int) -> list[LevelChange]:
        changes: list[LevelChange] = []
        for lv in self.active():
            if index - lv.last_index > self.cfg.level_max_age:
                lv.active = False
                changes.append(LevelChange(lv.id, "expirado", index))
        active = self.active()
        excess = len(active) - self.cfg.level_max_count
        if excess > 0:
            for lv in sorted(active, key=lambda x: (x.strength, x.last_index))[:excess]:
                lv.active = False
                changes.append(LevelChange(lv.id, "descartado", index))
        # Guarda só um histórico curto dos inativos para não crescer sem limite.
        inactive = [lv for lv in self._levels if not lv.active]
        if len(inactive) > self.cfg.level_max_count * 4:
            keep = {lv.id for lv in inactive[-self.cfg.level_max_count * 2 :]}
            self._levels = [lv for lv in self._levels if lv.active or lv.id in keep]
        return changes

    def nearest_support(self, price: float) -> Level | None:
        below = [lv for lv in self.active(Role.SUPPORT) if lv.price <= price]
        return max(below, key=lambda lv: (lv.price, lv.strength), default=None)

    def nearest_resistance(self, price: float) -> Level | None:
        above = [lv for lv in self.active(Role.RESISTANCE) if lv.price >= price]
        return min(above, key=lambda lv: (lv.price, -lv.strength), default=None)

    def zone(self, price: float) -> Zone:
        return Zone(price, self.nearest_support(price), self.nearest_resistance(price))

    def _find_near(self, price: float, role: Role, tol: float) -> Level | None:
        best: Level | None = None
        for lv in self.active(role):
            dist = abs(lv.price - price)
            if dist <= tol and (best is None or dist < abs(best.price - price)):
                best = lv
        return best
