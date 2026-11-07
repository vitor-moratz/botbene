from app.strategies.base import Direction, Signal, Strategy
from app.strategies.ldp_apostila import NAME as APOSTILA_NAME
from app.strategies.ldp_apostila import LdpApostila
from app.strategies.ldp_v13 import LdpV13
from app.strategies.ldp_v13_linhas import LdpV13Linhas
from app.strategies.recipes import RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO
from app.strategies.retracao_comando import NAME as RETRACAO_NAME
from app.strategies.score import NAME as SCORE_NAME
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
                              RETRACAO_LOTE, REVERSAO_FORCA, REVERSAO_INDECISAO, SCORE_NAME]

STRATEGY_LABELS: dict[str, str] = {
    LdpV13.name: "LDP v1.3",
    LdpV13Linhas.name: "LDP v1.3 + regra das linhas",
    WikiProV21.name: "WIKI PRO V2.1",
    APOSTILA_NAME: "Apostila · marcações",
    RETRACAO_NAME: "Apostila · retração no comando",
    RETRACAO_LOTE: "Estudo · retração no lote",
    REVERSAO_FORCA: "Estudo · reversão A (força trava)",
    REVERSAO_INDECISAO: "Estudo · reversão B (força rompe indecisão)",
    SCORE_NAME: "Score LDP v1 (combo)",
}

# Entrada que o usuário fez na mão. Fica só nas ordens: não é estratégia e nunca entra nas estatísticas delas.
MANUAL = "manual"


def default_strategies() -> list[Strategy]:
    return [cls() for cls in REGISTRY.values()]


__all__ = [
    "APOSTILA_NAME", "MANUAL", "RETRACAO_NAME", "REGISTRY", "SCORE_NAME", "STRATEGY_LABELS", "STRATEGY_ORDER", "Direction", "LdpApostila", "LdpV13",
    "LdpV13Linhas", "Signal", "Strategy", "WikiProV21", "default_strategies",
]
