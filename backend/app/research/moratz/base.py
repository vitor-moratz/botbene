"""Padrão Moratz: a base de velas M1 do laboratório (docs/padrao_moratz/README.md).

Tudo o que o laboratório mede sai de UM banco, data/moratz/velas_m1.sqlite:
- os ~60 dias de M1 de 09/09 a 08/11/2026 vieram do download de 08/11 (a IQ já não devolve setembro);
- `importar()` traz o M1 que o servidor arquiva em data/research.sqlite, aberto só em leitura;
- `baixar()` completa pela IQ, numa conexão própria e só na conta de treino.

As trilhas -op e OTC nunca se misturam: cada par pertence a uma só (`trilha_de`).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from app.config import get_settings
from app.market.candle import is_otc

BRT = ZoneInfo("America/Sao_Paulo")  # sem horário de verão desde 2019: UTC-3 o ano todo
BRT_OFFSET = -3 * 3600
TF = 60
TRILHAS = ("op", "otc")
NOME_TRILHA = {"op": "-op (mercado normal)", "otc": "OTC"}

# Payout de referência de cada trilha: o realizado nas ordens binárias do bot até 10/11/2026 (-op 0,83; OTC 0,832).
# Fica fixo de propósito: a régua não muda no meio do estudo. Empate = 1/(1+0,83) = 54,6%.
PAYOUT = {"op": 0.83, "otc": 0.83}

# Pares que pagavam 0,50 na binária em 10/11/2026 (empate em 66,7%): fora do estudo.
EXCLUIDOS = frozenset({"EURAUD-op", "USDCAD-op", "USDCHF-op"})

# Períodos em datas de Brasília, inclusive. D = descoberta (ler, mapear, ajustar à vontade);
# E = conferência (cada versão de regra roda aqui UMA vez). O futuro (F) começa no congelamento de cada versão.
PERIODOS = {"D": (date(2026, 9, 9), date(2026, 10, 18)), "E": (date(2026, 10, 19), date(2026, 11, 9))}

ESQUEMA = (
    "CREATE TABLE IF NOT EXISTS candles (asset VARCHAR(32) NOT NULL, timeframe INTEGER NOT NULL, ts INTEGER NOT NULL, "
    "open FLOAT NOT NULL, high FLOAT NOT NULL, low FLOAT NOT NULL, close FLOAT NOT NULL, volume FLOAT NOT NULL, "
    "PRIMARY KEY (asset, timeframe, ts))"
)
COLUNAS = "asset, timeframe, ts, open, high, low, close, volume"


def trilha_de(par: str) -> str:
    return "otc" if is_otc(par) else "op"


def pasta() -> Path:
    return get_settings().resolved_data_dir() / "moratz"


def banco_padrao() -> Path:
    return pasta() / "velas_m1.sqlite"


def limites(periodo: str) -> tuple[int, int]:
    """(início, fim) do período em epoch UTC; o fim é exclusivo (meia-noite do dia seguinte, Brasília)."""
    d0, d1 = PERIODOS[periodo]
    ini = datetime(d0.year, d0.month, d0.day, tzinfo=BRT)
    fim = datetime(d1.year, d1.month, d1.day, tzinfo=BRT) + timedelta(days=1)
    return int(ini.timestamp()), int(fim.timestamp())


def quando(ts: int) -> str:
    """Horário de Brasília de um timestamp, no formato do caderno."""
    return datetime.fromtimestamp(int(ts), BRT).strftime("%d/%m/%Y %H:%M")


def dia_brt(ts: np.ndarray) -> np.ndarray:
    """Número do dia (Brasília) de cada timestamp, para agrupar por par e dia."""
    return (np.asarray(ts, dtype=np.int64) + BRT_OFFSET) // 86400


@dataclass
class Serie:
    """Velas M1 de um par, em ordem. `ts` é o início da vela (epoch UTC)."""

    par: str
    ts: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741 (mínima da vela, como no gráfico)
    c: np.ndarray
    v: np.ndarray

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def trilha(self) -> str:
        return trilha_de(self.par)

    def ate(self, fim_ts: int) -> Serie:
        """Só as velas que começam antes de `fim_ts` (usado para provar que nada olha o futuro)."""
        k = int(np.searchsorted(self.ts, fim_ts, side="left"))
        return Serie(self.par, self.ts[:k], self.o[:k], self.h[:k], self.l[:k], self.c[:k], self.v[:k])

    @classmethod
    def de_velas(cls, par: str, velas: Iterable) -> Serie:
        """A partir de objetos com ts/open/high/low/close/volume (app.market.candle.Candle)."""
        rows = [(c.ts, c.open, c.high, c.low, c.close, getattr(c, "volume", 0.0)) for c in velas]
        a = np.array(rows, dtype=np.float64).reshape(-1, 6)
        return cls(par, a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5])


def _ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"Banco não encontrado: {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def pares(banco: Path | None = None, trilha: str | None = None, com_excluidos: bool = False) -> list[str]:
    with closing(_ro(banco or banco_padrao())) as con:
        rows = con.execute("SELECT DISTINCT asset FROM candles WHERE timeframe = ?", (TF,)).fetchall()
    return sorted(
        a for (a,) in rows
        if (trilha is None or trilha_de(a) == trilha) and (com_excluidos or a not in EXCLUIDOS)
    )


def carregar(trilha: str, pares_: Iterable[str] | None = None, banco: Path | None = None) -> dict[str, Serie]:
    """Velas M1 de cada par da trilha (todo o histórico do banco). Pares excluídos ficam fora, a não ser que
    sejam pedidos pelo nome."""
    if trilha not in TRILHAS:
        raise ValueError(f"Trilha desconhecida: {trilha} (use op ou otc)")
    banco = banco or banco_padrao()
    alvo = list(pares_) if pares_ is not None else pares(banco, trilha)
    out: dict[str, Serie] = {}
    with closing(_ro(banco)) as con:
        for par in alvo:
            if trilha_de(par) != trilha:
                raise ValueError(f"{par} não é da trilha {trilha}: as trilhas não se misturam")
            rows = con.execute(
                "SELECT ts, open, high, low, close, volume FROM candles "
                "WHERE asset = ? AND timeframe = ? AND ts % 60 = 0 ORDER BY ts",
                (par, TF),
            ).fetchall()
            if rows:
                a = np.array(rows, dtype=np.float64)
                out[par] = Serie(par, a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5])
    return out


def importar(origem: Path | None = None, destino: Path | None = None, sobra: int = 86400) -> dict[str, int]:
    """Traz o M1 novo do arquivo do servidor (research.sqlite) para o banco do laboratório.

    A origem é aberta só em leitura: nada é escrito nela. É incremental (a partir da última vela que já temos de
    cada par, menos `sobra` para fechar buracos recentes) e não altera velas que já existem. Pode rodar de novo
    a qualquer hora. Devolve quantas velas novas entraram por par."""
    origem = origem or get_settings().resolved_data_dir() / "research.sqlite"
    destino = destino or banco_padrao()
    destino.parent.mkdir(parents=True, exist_ok=True)
    novos: dict[str, int] = {}
    with closing(_ro(origem)) as src, closing(sqlite3.connect(destino)) as dst:
        dst.execute(ESQUEMA)
        series = [a for (a,) in src.execute("SELECT DISTINCT asset FROM candles WHERE timeframe = ?", (TF,))]
        for par in sorted(series):
            ultimo = dst.execute(
                "SELECT MAX(ts) FROM candles WHERE asset = ? AND timeframe = ?", (par, TF)
            ).fetchone()[0]
            desde = ultimo - sobra if ultimo else 0
            rows = src.execute(
                f"SELECT {COLUNAS} FROM candles WHERE asset = ? AND timeframe = ? AND ts >= ? AND ts % 60 = 0 "
                "ORDER BY ts",
                (par, TF, desde),
            ).fetchall()
            antes = dst.total_changes
            dst.executemany(f"INSERT OR IGNORE INTO candles ({COLUNAS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            novos[par] = dst.total_changes - antes
        dst.commit()
    return novos


def baixar(
    trilha: str,
    dias: int,
    pares_: Iterable[str] | None = None,
    destino: Path | None = None,
    progresso: Callable[[str, int, int, int], None] | None = None,
) -> dict[str, int]:
    """Completa o banco do laboratório direto da IQ (ela guarda ~60 dias de M1).

    Abre uma conexão PRÓPRIA, só na conta de treino (allow_real=False), em ritmo calmo, como o download de
    08/11/2026. É um segundo login na IQ: rode só com o OK do dono da conta."""
    from app.broker.iqoption import IQOptionBroker
    from app.db.database import Database
    from app.research.dataset import download
    from app.service.config_store import ConfigStore

    destino = destino or banco_padrao()
    alvo = list(pares_) if pares_ is not None else pares(destino, trilha)
    email, senha = ConfigStore(get_settings().resolved_data_dir() / "config.json").credentials()
    broker = IQOptionBroker(email, senha, allow_real=False, request_pause=0.5)
    broker.connect()
    db = Database(f"sqlite:///{destino}")
    agora = int(time.time())
    total: dict[str, int] = {}
    try:
        for par in alvo:
            if trilha_de(par) != trilha:
                raise ValueError(f"{par} não é da trilha {trilha}")
            if not broker.is_connected():
                broker.connect()
            total[par] = download(broker, db, par, TF, agora - dias * 86400, agora, progress=progresso)
    finally:
        broker.disconnect()
    return total


def ficha_da_base(banco: Path | None = None) -> list[dict]:
    """Uma linha por par: trilha, começo, fim, velas, buracos, velas paradas e volume."""
    banco = banco or banco_padrao()
    d_ini, d_fim = limites("D")
    e_ini, e_fim = limites("E")
    linhas = []
    for par in pares(banco, com_excluidos=True):
        s = carregar(trilha_de(par), [par], banco)[par]
        gaps = np.diff(s.ts)
        buracos = gaps > TF
        linhas.append({
            "par": par,
            "trilha": trilha_de(par),
            "excluido": par in EXCLUIDOS,
            "inicio": int(s.ts[0]),
            "fim": int(s.ts[-1]),
            "velas": len(s),
            "duplicadas": int((gaps == 0).sum()),
            "buracos": int(buracos.sum()),
            "buracos_longos": int((gaps >= 6 * 3600).sum()),  # fins de semana do -op e pausas longas
            "maior_buraco_h": float(gaps.max() / 3600) if len(gaps) else 0.0,
            "paradas": int(((s.o == s.h) & (s.h == s.l) & (s.l == s.c)).sum()),
            "volume_pct": float((s.v > 0).mean()),
            "velas_D": int(((s.ts >= d_ini) & (s.ts < d_fim)).sum()),
            "velas_E": int(((s.ts >= e_ini) & (s.ts < e_fim)).sum()),
        })
    return linhas


def payout_realizado(bot_db: Path | None = None) -> dict[str, tuple[float, int]]:
    """Só informação: mediana de lucro ÷ valor nas ordens GANHAS do bot, por trilha. A régua usa PAYOUT."""
    path = bot_db or get_settings().resolved_data_dir() / "botbene.sqlite"
    if not path.exists():
        return {}
    with closing(_ro(path)) as con:
        rows = con.execute("SELECT asset, profit, amount FROM orders WHERE status = 'win' AND amount > 0").fetchall()
    out: dict[str, tuple[float, int]] = {}
    for trilha in TRILHAS:
        vals = [p / a for par, p, a in rows if p and trilha_de(par) == trilha]
        if vals:
            out[trilha] = (float(np.median(vals)), len(vals))
    return out
