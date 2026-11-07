"""Score LDP v1: o combo arma só com a retração no comando e 3 de 4 padrões; pula dizendo o que faltou."""

import pytest

from app.ldp.engine import LdpEngine
from app.market.candle import Candle
from app.strategies.base import Direction
from app.strategies.intra import replay, run_intra, watch_forming
from app.strategies.ldp_apostila import backtest, gap_ok, simulate_entry, touched
from app.strategies.score import NAME, ScoreLdp, ScoreSetup
from tests.helpers import seq

CALM = [(10.00, 10.06, 9.96, 10.02), (10.02, 10.06, 9.96, 10.00)] * 8
STRONG = (10.00, 10.20, 10.00, 10.18)  # verde forte, 2 ATR: a retração no comando arma CALL
CANDLES = seq(*CALM, STRONG)
K = len(CANDLES) - 1


def subs(start, *rows):
    return [Candle(start + 5 * i, o, h, lo, c) for i, (o, h, lo, c) in enumerate(rows)]


def setup(direction=Direction.CALL, target=1_000_060, parts=None, prev_close=10.18):
    parts = parts or [(10.15, 0.005, None, 0.02), (0.0, 0.0, 0.08, 0.02)]
    s = ScoreSetup(direction=direction, trigger="score", level_price=0.0, level_strength=2, level_sources=["3 de 4"],
                   decision_index=0, decision_ts=target - 60, target_ts=target, window_seconds=15, touch_tol=0.0,
                   prev_close=prev_close, prev_range=0.20, gap_tol_pct=0.0, strategy=NAME, open_offset=0.08,
                   gap_floor=max(p[3] for p in parts), parts=parts)
    s.level_price = s.level_for_open(prev_close)
    return s


def test_gatilho_e_o_primeiro_toque_entre_as_marcacoes():
    s = setup()
    # região em 10.15 (+ tolerância 0.005) fica acima do recuo do comando (10.19 − 0.08 = 10.11): o preço encontra ela antes
    assert s.level_for_open(10.19) == pytest.approx(10.155)
    put = setup(Direction.PUT, parts=[(10.25, 0.005, None, 0.02), (0.0, 0.0, 0.08, 0.02)])
    assert put.level_for_open(10.19) == pytest.approx(10.245)  # no PUT, a mais baixa: 10.19 + 0.08 = 10.27 > 10.245


def test_parte_em_gap_sai_do_conjunto():
    s = setup(parts=[(10.15, 0.005, None, 0.005), (0.0, 0.0, 0.08, 0.02)])
    assert s.level_for_open(10.19) == pytest.approx(10.11)  # a região só tolera 0.005 de GAP; abriu 0.01 longe
    assert gap_ok(s, 10.19) and not gap_ok(s, 10.25)


def test_simulacao_usa_o_conjunto():
    s = setup()
    entry, why = simulate_entry(s, subs(s.target_ts, (10.19, 10.19, 10.17, 10.18), (10.18, 10.18, 10.15, 10.16)))
    assert (entry, why) == (10.16, "tocou")


def test_pula_e_diz_o_que_faltou():
    plan = run_intra(CANDLES, [ScoreLdp()])[1][K]
    assert not plan.armed
    assert plan.reasons and plan.reasons[0].startswith("Score: pulou CALL · 2 de 4")
    note = plan.skipped[0]
    assert note["strategy"] == NAME and note["direction"] == "call" and note["target_ts"] == CANDLES[K].ts + 60
    assert note["outcome"].startswith("pulou: ") and "de 4" in note["outcome"]
    # rompeu a máxima das 10 velas (10.20 > 10.06) e, sem os primeiros 15 s das velas, não há recorrência
    assert "✗ comando dentro das 10 velas" in note["outcome"] and "✗ recorrência do par" in note["outcome"]
    assert "sem dados dos 15 s" in note["outcome"]


def test_sem_comando_nao_avalia():
    plan = run_intra(seq(*CALM), [ScoreLdp()])[1][-1]
    assert not plan.armed and not plan.skipped


def test_recorrencia_precisa_de_10_entradas_e_6_acertos():
    s = ScoreLdp()
    s.recent.extend([True] * 6 + [False] * 3)
    assert not s._recurrence_ok()  # só 9
    s.recent.append(False)
    assert s._recurrence_ok() and s.recurrence == (6, 10)
    s.recent.append(False)  # sai o acerto mais antigo: 5 de 10
    assert not s._recurrence_ok()


def test_recorrencia_conta_o_lado_escolhido_com_os_primeiros_15_s():
    s = ScoreLdp()
    p = setup()
    s._pending = p
    s.watch_window(p.target_ts, subs(p.target_ts, (10.19, 10.19, 10.17, 10.18), (10.18, 10.18, 10.15, 10.16)))
    s._settle(Candle(p.target_ts, 10.19, 10.25, 10.10, 10.22))
    assert list(s.recent) == [True]  # entrou em 10.16, fechou em 10.22
    s._pending = p = setup(target=p.target_ts + 60)
    s.watch_window(p.target_ts, subs(p.target_ts, (10.30, 10.30, 10.10, 10.12)))  # GAP: não conta
    s._settle(Candle(p.target_ts, 10.30, 10.30, 10.10, 10.12))
    assert list(s.recent) == [True]


def test_ao_vivo_so_vale_dentro_da_janela():
    s = ScoreLdp()
    s._pending = p = setup()
    late = Candle(p.target_ts, 10.19, 10.19, 10.14, 10.15)
    watch_forming([s], late, now=p.target_ts + 20)  # já passou dos 15 s
    s._settle(Candle(p.target_ts, 10.19, 10.25, 10.10, 10.22))
    assert not s.recent
    s._pending = p = setup(target=p.target_ts + 60)
    watch_forming([s], Candle(p.target_ts, 10.19, 10.19, 10.17, 10.18), now=p.target_ts + 3)
    watch_forming([s], Candle(p.target_ts, 10.19, 10.19, 10.15, 10.16), now=p.target_ts + 9)
    s._settle(Candle(p.target_ts, 10.19, 10.20, 10.10, 10.12))
    assert list(s.recent) == [False]  # entrou em 10.16, fechou em 10.12


def test_replay_entrega_a_janela_antes_do_fechamento():
    calls = []

    class Spy:
        name, needs_windows = "spy", True

        def watch_window(self, ts, inside):
            calls.append(("janela", ts, len(inside)))

        def on_step(self, step, engine):
            calls.append(("vela", step.info.candle.ts))
            from app.strategies.ldp_apostila import Plan
            return Plan(step.index, [], [])

    candles = seq(*CALM[:3])
    sub = subs(candles[1].ts, (10.0, 10.0, 10.0, 10.0), (10.0, 10.0, 10.0, 10.0))
    replay([Spy()], LdpEngine(), candles, sub)
    assert calls[2:4] == [("janela", candles[1].ts, 2), ("vela", candles[1].ts)]


def test_bot_com_score_busca_os_5_s_antes_de_processar_o_historico(tmp_path):
    from tests.test_retroativo import DAY_START, NOW, ClockBroker, candles_between, make_bot

    broker = ClockBroker(candles_between(NOW - 2 * 86400, NOW), sub=candles_between(NOW - 86400, NOW, 5))
    bot = make_bot(tmp_path, broker)
    bot.config.update({"strategies": {"score_ldp": "operate"}})
    bot.configure(["EURUSD-OTC"], 60)
    bot._bootstrap(broker)
    assert broker.asked[5] == [(NOW - (DAY_START - 2 * 3600) + 60) // 5]  # uma busca só, desde 2 h antes da meia-noite
    assert [s.name for s in bot.runner().intra] == [NAME]


def test_bot_anota_os_pulos_do_score(tmp_path):
    from tests.test_bot_service import make_bot

    bot, broker, _, _ = make_bot(tmp_path, n_live=240, closing=False, strategies={"score_ldp": "operate"})
    bot._bootstrap(broker)
    for _ in range(240):
        bot._poll(broker)
    skipped = [x for x in bot.armed_log if x["outcome"].startswith("pulou")]
    assert skipped and all(x["strategy"] == NAME and x["asset"] == "EURUSD" and ("de 4" in x["outcome"] or "pontos" in x["outcome"])
                           for x in skipped)


def test_backtest_com_janelas_entra_no_toque():
    nxt = (10.18, 10.24, 10.09, 10.22)
    candles = CANDLES + seq(nxt, start_ts=CANDLES[-1].ts + 60)
    t = candles[-1].ts
    sub = subs(t, (10.18, 10.18, 10.12, 10.13), (10.13, 10.13, 10.09, 10.10), (10.10, 10.24, 10.10, 10.22))
    _, plans = run_intra(candles, [ScoreLdp()], subs=sub)
    assert not backtest(candles, plans, sub)  # pulou (rompeu as 10 velas, sem recorrência): não entra
    assert touched(setup(), 10.15, 10.19)
