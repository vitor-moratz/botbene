"""Motor da apostila "Estudos e anotações sobre a Lógica do Preço".

Cada regra cita a página da apostila de onde saiu. Tudo aqui usa apenas velas
fechadas e o passado, então um resultado já calculado nunca muda (sem repintura).
"""

from app.ldp.candles import CandleClass, CandleInfo, classify
from app.ldp.config import LdpConfig
from app.ldp.engine import EngineStep, LdpEngine
from app.ldp.levels import Level, LevelMap, Role, Zone
from app.ldp.structures import Mark, Structure

__all__ = [
    "CandleClass",
    "CandleInfo",
    "EngineStep",
    "LdpConfig",
    "LdpEngine",
    "Level",
    "LevelMap",
    "Mark",
    "Role",
    "Structure",
    "Zone",
    "classify",
]
