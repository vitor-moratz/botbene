"""Horário de Nova York, para estratégias que vivem no fechamento do dia do forex (17h de NY).

O fechamento de NY anda no horário de Brasília quando os EUA entram ou saem do horário de verão:
17h de NY = 18h de Brasília de março a novembro e 19h de Brasília de novembro a março.
Seguindo NY, a janela se acerta sozinha.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def hora_ny(ts: int) -> int:
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(NY).hour


def na_janela(ts: int, horas: range) -> bool:
    """`ts` = início da vela de entrada (epoch UTC); `horas` = horas cheias de NY aceitas."""
    return hora_ny(ts) in horas
