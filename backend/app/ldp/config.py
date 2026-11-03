from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LdpConfig:
    """Parâmetros do motor. Os valores iniciais serão ajustados com estatística, um por vez."""

    # Pavio menor ou igual a esta fração da amplitude conta como "sem pavio" (vela careca).
    # 2% é o mesmo padrão do script LDP v1.3.
    wick_tol_pct: float = 0.02
    # Corpo menor que esta fração da amplitude: vela sem cor (doji/pião).
    doji_body_pct: float = 0.05
    # Vela com pavio dos dois lados é "vela de força" se o corpo for pelo menos esta fração (pág. 11-13, 16).
    forca_min_body_pct: float = 0.40
    # Abertura afastada do fechamento anterior mais que esta fração da amplitude anterior = GAP (pág. 28).
    gap_tol_pct: float = 0.10
    # Nova alta/baixa: o corpo precisa fechar além das máximas/mínimas destas últimas velas (pág. 97-99).
    breakout_window: int = 5
    # Velas usadas para dizer se uma vela está num topo ou fundo local (TD de topo/fundo, pág. 50-53).
    extreme_lookback: int = 5
    # Pavio a partir desta fração da amplitude é "pavio grande": marca ponta e 50% (pág. 138, item i).
    big_wick_pct: float = 0.50
    # Validade das marcações, em velas, e quantidade máxima mantida.
    level_max_age: int = 180
    level_max_count: int = 80
    # Marcações a menos de (fração × ATR) uma da outra viram uma só, mais forte.
    merge_tol_atr: float = 0.05
    atr_period: int = 14
