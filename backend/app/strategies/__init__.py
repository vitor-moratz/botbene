from app.strategies.base import Direction, Signal, Strategy
from app.strategies.bb_rci import NAME as BB_RCI_NAME
from app.strategies.bb_rci_ny import NAME as BB_RCI_NY_NAME
from app.strategies.bb_rci_v2 import NAME as BB_RCI_V2_NAME
from app.strategies.deeplob import NAME as DEEPLOB_NAME
from app.strategies.esticao import NAME as ESTICAO_NAME
from app.strategies.ldp_apostila import NAME as APOSTILA_NAME
from app.strategies.ldp_apostila import LdpApostila
from app.strategies.ldp_v13 import LdpV13
from app.strategies.ldp_v13_linhas import LdpV13Linhas
from app.strategies.recipes import RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO
from app.strategies.retracao_comando import NAME as RETRACAO_NAME
from app.strategies.retracao_comando import NAME_V2 as RETRACAO_V2_NAME
from app.strategies.score import NAME as SCORE_NAME
from app.strategies.virada_tarde import NAME as VIRADA_NAME
from app.strategies.wiki_pro_v21 import WikiProV21

# Scripts que dão sinal no FECHAMENTO da vela (entrada na abertura da seguinte).
REGISTRY: dict[str, type[Strategy]] = {
    LdpV13.name: LdpV13,
    LdpV13Linhas.name: LdpV13Linhas,
    WikiProV21.name: WikiProV21,
}

# Ordem fixa de todos os scripts no painel (a cor segue o script, nunca a posição).
# As duas da apostila entram DENTRO da vela (gatilho de 15 s) e são tratadas à parte pelo bot.
STRATEGY_ORDER: list[str] = [LdpV13.name, LdpV13Linhas.name, WikiProV21.name, APOSTILA_NAME, RETRACAO_NAME,
                              RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO, SCORE_NAME, RETRACAO_V2_NAME, ESTICAO_NAME,
                              DEEPLOB_NAME, BB_RCI_NAME, BB_RCI_V2_NAME, VIRADA_NAME, BB_RCI_NY_NAME]

STRATEGY_LABELS: dict[str, str] = {
    LdpV13.name: "LDP v1.3",
    LdpV13Linhas.name: "LDP v1.3 + regra das linhas",
    WikiProV21.name: "WIKI PRO V2.1",
    APOSTILA_NAME: "Apostila · marcações",
    RETRACAO_NAME: "Apostila · retração no comando",
    RETRACAO_V2_NAME: "Apostila · retração no comando v2",
    RETRACAO_LOTE: "Estudo · retração no lote",
    REVERSAO_FORCA: "Estudo · reversão A (força trava)",
    REVERSAO_INDECISAO: "Estudo · reversão B (força rompe indecisão)",
    SCORE_NAME: "Score LDP v1 (combo)",
    ESTICAO_NAME: "Pesquisa · esticão rápido",
    DEEPLOB_NAME: "Pesquisa · DeepLOB (IA)",
    BB_RCI_NAME: "Pesquisa · Bollinger + RCI",
    BB_RCI_V2_NAME: "Pesquisa · Bollinger + RCI v2",
    VIRADA_NAME: "Padrão Moratz · Virada da Tarde",
    BB_RCI_NY_NAME: "Bollinger + RCI · fechamento NY",
}

# Entrada que o usuário fez na mão. Fica só nas ordens: não é estratégia e nunca entra nas estatísticas delas.
MANUAL = "manual"


def default_strategies() -> list[Strategy]:
    return [cls() for cls in REGISTRY.values()]


__all__ = [
    "APOSTILA_NAME", "MANUAL", "RETRACAO_NAME", "RETRACAO_V2_NAME", "REGISTRY", "SCORE_NAME", "STRATEGY_LABELS", "STRATEGY_ORDER", "Direction", "LdpApostila", "LdpV13",
    "LdpV13Linhas", "Signal", "Strategy", "WikiProV21", "default_strategies",
]
