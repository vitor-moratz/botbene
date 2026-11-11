"""Padrão Moratz: o laboratório não pode olhar o futuro, nem misturar trilhas, nem deixar o E ser visto duas vezes."""

from __future__ import annotations

import hashlib
import json
import sqlite3

import numpy as np
import pytest

from app.config import Settings
from app.paper import DRAW, LOSS, WIN, judge
from app.research.moratz import base, caderno
from app.research.moratz.alvo import cinco, proxima, resultado
from app.research.moratz.base import Serie, limites
from app.research.moratz.mapa import embaralhar, juntar, mapa
from app.research.moratz.medir import coletar, preparar, resumo, sorteio, veredito_futuro
from app.research.moratz.mesa import ANTES, DEPOIS, momentos
from app.research.moratz.regra import aplicar, hash_regra, validar
from app.research.moratz.tracos import DICIONARIO, tracos
from app.tools import moratz as tool
from tests.helpers import random_walk, seq

BASE_TS = 1_699_999_980  # múltiplo de 60, como as velas da IQ


def serie(velas, par="EURUSD-op", inicio=BASE_TS) -> Serie:
    s = Serie.de_velas(par, velas)
    s.ts = inicio + 60 * np.arange(len(s), dtype=np.int64)
    return s


def regra(**kw) -> dict:
    r = {"id": "T-1", "trilha": "op", "texto": "teste", "condicoes": [{"traco": "cor", "em": [1]}],
         "direcao": "call"}
    r.update(kw)
    return validar(r)


def _iguais(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(a[~np.isnan(a)], b[~np.isnan(b)]))


# ---------- traços: só o passado ----------

@pytest.mark.parametrize("corte", [437, 450, 451, 599])
def test_tracos_nao_olham_o_futuro(corte):
    """O traço da vela k é o mesmo com ou sem as velas depois de k, inclusive o contexto M5/M15."""
    s = serie(random_walk(700, seed=3))
    cheio = tracos(s)
    parcial = tracos(s.ate(int(s.ts[corte])))
    for nome in (*DICIONARIO, "unidade"):
        assert _iguais(cheio[nome][:corte], parcial[nome]), nome


def test_contexto_m15_so_conta_vela_maior_fechada_e_completa():
    s = serie(random_walk(400, seed=5))
    t = tracos(s)
    for k in range(60, 400):
        fim_k = int(s.ts[k]) + 60
        bloco = fim_k // 900 - 1  # a M15 que terminou até o fechamento de k
        idx = np.flatnonzero(s.ts // 900 == bloco)
        assert s.ts[idx[-1]] + 60 <= fim_k  # nunca uma vela depois de k
        if len(idx) == 15 and t["pronta"][k]:
            assert t["ctx15_mov"][k] == pytest.approx((s.c[idx[-1]] - s.o[idx[0]]) / t["unidade"][k])
    # uma M15 incompleta (buraco no meio) não vale como contexto
    furada = serie(random_walk(400, seed=5))
    furada.ts = furada.ts.copy()
    furada.ts[200:] += 60  # buraco de 1 min na vela 200
    t2 = tracos(furada)
    blocos = furada.ts // 900
    alvo = (furada.ts + 60) // 900 - 1
    incompletos = {b for b in np.unique(blocos) if (blocos == b).sum() != 15}
    for k in range(len(furada)):
        if alvo[k] in incompletos:
            assert np.isnan(t2["ctx15_mov"][k])


def test_vela_so_fica_pronta_com_20_anteriores_sem_buraco():
    s = serie(random_walk(100, seed=1))
    s.ts = s.ts.copy()
    s.ts[50:] += 3600  # pausa de 1 h
    t = tracos(s)
    assert not t["pronta"][:20].any()
    assert t["pronta"][20:50].all()
    assert not t["pronta"][50:70].any()
    assert t["pronta"][70:].all()
    assert np.isnan(t["tamanho"][55])


def test_fila_conta_cores_seguidas_e_zera_no_buraco():
    velas = seq(*([(1.0, 1.1, 0.9, 1.05)] * 3 + [(1.05, 1.1, 0.9, 1.0)] * 2 + [(1.0, 1.0, 1.0, 1.0)]))
    s = serie(velas)
    t = tracos(s)
    # nenhuma está pronta (menos de 20 velas), então a fila crua é conferida pelo helper interno
    from app.research.moratz.tracos import _fila
    assert _fila(s.ts, np.sign(s.c - s.o).astype(int)).tolist() == [1, 2, 3, -1, -2, 0]
    assert np.isnan(t["fila"]).all()


# ---------- alvo: a vela seguinte ----------

def test_resultado_e_a_vela_seguinte_e_bate_com_a_judge_do_bot():
    velas = seq((1.0, 1.2, 0.9, 1.1), (1.1, 1.3, 1.0, 1.25), (1.25, 1.3, 1.1, 1.15), (1.15, 1.2, 1.1, 1.15),
                (1.15, 1.2, 1.1, 1.18))
    s = serie(velas)
    valida, sobe = proxima(s)
    assert valida.tolist() == [True, True, True, True, False]
    assert sobe.tolist() == [1, -1, 0, 1, 0]
    for k in range(4):
        for direcao, nome in ((1, "call"), (-1, "put")):
            r = int(resultado(np.array([direcao]), np.array([sobe[k]]))[0])
            esperado = judge(nome, s.o[k + 1], s.c[k + 1])
            assert {WIN: 1, LOSS: -1, DRAW: 0}[esperado] == r


def test_resultado_nao_atravessa_buraco():
    s = serie(seq(*([(1.0, 1.1, 0.9, 1.05)] * 4)))
    s.ts = s.ts.copy()
    s.ts[2:] += 60
    valida, _ = proxima(s)
    assert valida.tolist() == [True, False, True, False]
    v5, _ = cinco(serie(random_walk(12)))
    assert v5.tolist() == [True] * 7 + [False] * 5


# ---------- regra ----------

def test_regra_dispara_so_na_vela_grande_que_fecha_no_topo():
    calmas = [(1.0, 1.001, 0.999, 1.0005)] * 24
    grande = (1.0005, 1.0045, 1.0, 1.0044)  # amplitude 4,5x a unidade, fecha quase na máxima
    depois = (1.0044, 1.0046, 1.002, 1.0021)
    s = serie(seq(*calmas, grande, depois))
    t = tracos(s)
    r = regra(condicoes=[{"traco": "tamanho", "min": 2.0}, {"traco": "fecho", "min": 0.9}], direcao="contra_cor")
    dispara, direcao = aplicar(r, t)
    assert np.flatnonzero(dispara).tolist() == [24]
    assert direcao[24] == -1  # vela verde: contra a cor = PUT
    prep = preparar({"EURUSD-op": s})
    sinais = coletar(r, prep, None, None)
    assert sinais.res.tolist() == [1]  # a seguinte desceu


def test_hash_muda_com_numero_e_nao_com_texto():
    a = regra()
    assert hash_regra(a) == hash_regra({**a, "texto": "outro jeito de dizer", "id": "X"})
    assert hash_regra(a) != hash_regra({**a, "condicoes": [{"traco": "cor", "em": [-1]}]})
    assert hash_regra(a) != hash_regra({**a, "direcao": "put"})


def test_validar_recusa_traco_inventado_e_par_de_outra_trilha():
    with pytest.raises(ValueError, match="dicionário"):
        regra(condicoes=[{"traco": "martelo", "min": 1}])
    with pytest.raises(ValueError, match="trilha"):
        regra(pares=["EURUSD-OTC"])
    with pytest.raises(ValueError, match="0,50"):
        regra(pares=["USDCAD-op"])


def test_carregar_nao_mistura_trilhas(tmp_path):
    banco = _banco(tmp_path, {"EURUSD-op": random_walk(30), "EURUSD-OTC": random_walk(30, seed=2)})
    assert list(base.carregar("op", banco=banco)) == ["EURUSD-op"]
    assert list(base.carregar("otc", banco=banco)) == ["EURUSD-OTC"]
    with pytest.raises(ValueError, match="não se misturam"):
        base.carregar("op", ["EURUSD-OTC"], banco=banco)


# ---------- sorteio e mapa ----------

def _velas(n, seed, regra_cor, par="EURUSD-op", inicio=BASE_TS) -> Serie:
    rng = np.random.default_rng(seed)
    o = np.empty(n)
    c = np.empty(n)
    preco = 1.1
    for i in range(n):
        o[i] = preco
        sobe = regra_cor(i, c[i - 1] > o[i - 1] if i else False, rng)
        c[i] = preco + sobe * rng.uniform(0.0002, 0.0008)
        preco = c[i]
    h = np.maximum(o, c) + rng.uniform(0, 0.0003, n)
    lo = np.minimum(o, c) - rng.uniform(0, 0.0003, n)
    return Serie(par, inicio + 60 * np.arange(n, dtype=np.int64), o, h, lo, c, np.zeros(n))


def _acaso(n=3000, seed=4, par="EURUSD-op") -> Serie:
    """Cara ou coroa a cada vela: não existe padrão nenhum."""
    return _velas(n, seed, lambda i, verde, rng: rng.choice((-1, 1)), par)


def _plantado(n=3000, seed=4, par="EURUSD-op") -> Serie:
    """Padrão plantado: depois de uma vela verde vem sempre uma vermelha; depois da vermelha, cara ou coroa.
    Por isso só 1/3 das velas sobem, e o sorteio precisa levar isso em conta."""
    return _velas(n, seed, lambda i, verde, rng: -1 if verde else rng.choice((-1, 1)), par)


def test_sorteio_aponta_o_padrao_plantado_e_nao_se_engana_com_a_base():
    r = regra(condicoes=[{"traco": "cor", "em": [1]}], direcao="contra_cor")
    prep = preparar({"EURUSD-op": _plantado()})
    s = coletar(r, prep, None, None)
    res = resumo(s, 0.83, 3)
    assert res["acerto"] == 1.0
    sort = sorteio(s, prep, None, None, vezes=100)
    assert sort["p"] <= 0.01
    # só 1/3 das velas sobem: apostar PUT "às cegas" já dá ~2/3, e o sorteio sabe disso
    assert 0.6 < sort["media"] < 0.73

    acaso = preparar({"EURUSD-op": _acaso(seed=9)})
    s2 = coletar(r, acaso, None, None)
    sort2 = sorteio(s2, acaso, None, None, vezes=100)
    assert sort2["p"] > 0.01


def test_embaralhar_mantem_as_altas_de_cada_par_e_dia():
    prep = preparar({"EURUSD-op": serie(random_walk(4000, seed=2)),
                     "GBPUSD-op": serie(random_walk(4000, seed=8), par="GBPUSD-op")})
    tab = juntar(prep, None, None)
    novo = embaralhar(tab, np.random.default_rng(1))
    for bloco in np.unique(tab["bloco"]):
        m = tab["bloco"] == bloco
        assert sorted(novo[m].tolist()) == sorted(tab["sobe"][m].tolist())
    assert (novo != tab["sobe"]).any()


def test_mapa_fica_perto_de_50_no_acaso_e_ve_o_plantado():
    acaso = preparar({f"P{i}-op": _acaso(5000, seed=i, par=f"P{i}-op") for i in range(3)})
    m = mapa(acaso, None, None, sorteios=3)
    assert 0.47 < m["base_alta"] < 0.53
    assert set(m["real"]["simples"]) >= {"tamanho", "fecho", "fila", "hora"}
    assert "vol_rel" not in m["real"]["simples"]  # sem volume: o traço some
    assert m["resumo"]["real"]["continua"] <= m["resumo"]["sorteio_max"]["continua"] + 3

    plantado = preparar({"EURUSD-op": _plantado(5000)})
    m2 = mapa(plantado, None, None, sorteios=2)
    verde = m2["real"]["simples"]["cor"]["celulas"][2]
    assert verde["continua"] == 0.0  # verde sempre vira
    assert 0.2 < m2["sorteio"]["simples"]["cor"]["celulas"][2]["continua"] < 0.45


# ---------- mesa ----------

def test_mesa_sorteia_momentos_com_o_futuro_separado():
    s = serie(random_walk(3000, seed=6))
    prep = preparar({"EURUSD-op": s})
    lote = momentos(prep, "op", int(s.ts[0]), int(s.ts[-1]) + 60, quantos=20)
    assert len(lote) == 20
    assert len({m["id"] for m in lote}) == 20
    for m in lote:
        k = int(np.searchsorted(s.ts, m["ts"]))
        assert len(m["velas"]) == ANTES + DEPOIS
        esc = 10 ** m["casas"]
        assert (m["base"] + m["velas"][ANTES - 1][3]) / esc == pytest.approx(s.c[k], abs=1 / esc)
        assert (m["base"] + m["velas"][ANTES][0]) / esc == pytest.approx(s.o[k + 1], abs=1 / esc)
        assert m["sobe"] == int(np.sign(s.c[k + 1] - s.o[k + 1]))
        assert m["regua"]["tamanho"] == pytest.approx(prep["EURUSD-op"].t["tamanho"][k], abs=1e-3)


# ---------- base: importar só lê a origem ----------

def _banco(pasta, series: dict, inicio=BASE_TS):
    path = pasta / f"b{len(list(pasta.iterdir()))}.sqlite"
    con = sqlite3.connect(path)
    con.execute(base.ESQUEMA)
    for par, velas in series.items():
        con.executemany(
            "INSERT INTO candles VALUES (?, 60, ?, ?, ?, ?, ?, ?)",
            [(par, inicio + 60 * i, v.open, v.high, v.low, v.close, 0.0) for i, v in enumerate(velas)],
        )
    con.commit()
    con.close()
    return path


def test_importar_nao_escreve_na_origem_e_e_incremental(tmp_path):
    origem = _banco(tmp_path, {"EURUSD-op": random_walk(50), "EURUSD-OTC": random_walk(50, seed=3)})
    antes = hashlib.md5(origem.read_bytes()).hexdigest()
    destino = tmp_path / "lab.sqlite"
    novos = base.importar(origem, destino)
    assert novos == {"EURUSD-OTC": 50, "EURUSD-op": 50}
    assert hashlib.md5(origem.read_bytes()).hexdigest() == antes
    assert sum(base.importar(origem, destino).values()) == 0


# ---------- futuro, conferência e caderno ----------

def test_futuro_so_conta_depois_do_congelamento_e_tampa_o_placar():
    s = serie(random_walk(800, seed=12))
    prep = preparar({"EURUSD-op": s})
    desde = int(s.ts[400])
    sinais = coletar(regra(), prep, desde, None)
    assert len(sinais) and (sinais.ts >= desde).all()
    r = {"n": 80, "acerto": 0.9, "ic": [0.8, 0.95], "empate": 0.546}
    assert veredito_futuro(r)[0] == "juntando" and "tampado" in veredito_futuro(r)[1]
    assert veredito_futuro({**r, "n": 150, "acerto": 0.45})[0] == "caiu"
    assert veredito_futuro({**r, "n": 210, "acerto": 0.63, "ic": [0.56, 0.69]})[0] == "passou"
    assert veredito_futuro({**r, "n": 210, "acerto": 0.53, "ic": [0.46, 0.6]})[0] == "caiu"
    assert veredito_futuro({**r, "n": 210, "acerto": 0.57, "ic": [0.50, 0.64]})[0] == "juntando"


def test_janela_nao_deixa_entrada_atravessar_o_fim_do_periodo():
    s = serie(random_walk(300, seed=2))
    prep = preparar({"EURUSD-op": s})
    fim = int(s.ts[200])
    sinais = coletar(regra(direcao="call", condicoes=[{"traco": "cor", "em": [-1, 0, 1]}]), prep, None, fim)
    assert (sinais.ts + 120 <= fim).all()
    assert sinais.ts[-1] == s.ts[198]  # decide em 198, entra em 199, que fecha exatamente no fim


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Pasta de dados e caderno de mentira, com um par -op que tem velas em D e em E."""
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    monkeypatch.setattr(base, "get_settings", lambda: settings)
    monkeypatch.setattr(caderno, "PASTA", tmp_path / "docs")
    d_ini, _ = limites("D")
    e_ini, _ = limites("E")
    lab_dir = tmp_path / "data" / "moratz"
    lab_dir.mkdir(parents=True)
    con = sqlite3.connect(lab_dir / "velas_m1.sqlite")
    con.execute(base.ESQUEMA)
    for inicio, semente in ((d_ini, 1), (e_ini, 2)):
        for i, v in enumerate(random_walk(600, seed=semente)):
            con.execute("INSERT INTO candles VALUES ('EURUSD-op', 60, ?, ?, ?, ?, ?, 0)",
                        (inicio + 60 * i, v.open, v.high, v.low, v.close))
    con.commit()
    con.close()
    path = tmp_path / "regra.json"
    path.write_text(json.dumps({"id": "T-9", "trilha": "op", "texto": "verde puxa verde",
                                "condicoes": [{"traco": "cor", "em": [1]}], "direcao": "a_favor_cor"}))
    return path


def test_testar_registra_no_caderno_e_conferir_exige_a_porta_e_trava(lab, capsys):
    tool.main(["testar", str(lab), "--variacoes", "3", "--nota", "primeira"])
    entradas = caderno.ler(caderno.PASTA)
    assert entradas[-1]["tipo"] == "teste_D" and entradas[-1]["variacoes"] == 3
    assert "Teste em D" in (caderno.PASTA / "caderno.md").read_text()
    assert entradas[-1]["porta"] is False  # passeio aleatório não passa
    with pytest.raises(SystemExit, match="porta em D"):
        tool.main(["conferir", str(lab)])
    # simula a porta aberta em D para provar a trava do E
    h = hash_regra(validar(json.loads(lab.read_text())))
    caderno.registrar({"tipo": "teste_D", "hash": h, "trilha": "op", "porta": True}, caderno.PASTA)
    tool.main(["conferir", str(lab)])
    with pytest.raises(SystemExit, match="uma vez só"):
        tool.main(["conferir", str(lab)])
    with pytest.raises(SystemExit, match="passou a porta em E"):
        tool.main(["congelar", str(lab), "--versao", "0.1"])


def test_ver_esconde_o_que_veio_depois_no_periodo_e(lab, capsys):
    e_ini, _ = limites("E")
    tool.main(["ver", "EURUSD-op", base.quando(e_ini + 60 * 300)])
    saida = capsys.readouterr().out
    assert "fica escondido" in saida and "  depois " not in saida
    d_ini, _ = limites("D")
    tool.main(["ver", "EURUSD-op", base.quando(d_ini + 60 * 300)])
    assert "vela de entrada" in capsys.readouterr().out


def test_entrada_5s_usa_a_primeira_vela_de_5s_da_entrada(tmp_path):
    """A conferência mede também a entrada como o bot faz: no fechamento da 1ª vela de 5 s de k+1."""
    from app.research.moratz.medir import com_entrada_5s
    s = serie(random_walk(60, seed=4))
    prep = preparar({"EURUSD-op": s})
    sinais = coletar(regra(condicoes=[{"traco": "cor", "em": [-1, 0, 1]}]), prep, None, None)  # CALL em tudo
    origem = tmp_path / "research.sqlite"
    con = sqlite3.connect(origem)
    con.execute(base.ESQUEMA)
    # 5 s só para as duas primeiras entradas: a 1ª abaixo do fechamento (ganha), a 2ª acima (perde)
    for i, delta in ((0, -0.001), (1, +0.001)):
        ts = int(sinais.ts[i]) + 60
        con.execute("INSERT INTO candles VALUES ('EURUSD-op', 5, ?, 1, 1, 1, ?, 0)", (ts, float(sinais.saida[i]) + delta))
    con.commit()
    con.close()
    r5 = com_entrada_5s(sinais, origem)
    assert r5["n"] == 2 and r5["acerto"] == 0.5
    assert r5["cobertura"] == pytest.approx(2 / len(sinais))


def test_lote_novo_sorteia_outros_momentos_com_ids_proprios():
    s = serie(random_walk(3000, seed=6))
    prep = preparar({"EURUSD-op": s})
    ini, fim = int(s.ts[0]), int(s.ts[-1]) + 60
    l1 = momentos(prep, "op", ini, fim, quantos=10)
    l2 = momentos(prep, "op", ini, fim, quantos=10, lote=2)
    assert all(m["id"].startswith("op-") and "-L" not in m["id"] for m in l1)
    assert all(m["id"].startswith("op-L2-") for m in l2)
    assert {m["ts"] for m in l1} != {m["ts"] for m in l2}
    assert [m["ts"] for m in momentos(prep, "op", ini, fim, quantos=10)] == [m["ts"] for m in l1]  # mesma semente, mesmo lote


# ---------- Virada da Tarde no bot ----------

def _plano_virada(fecho_alvo, hora_entrada, par="EURUSD-op"):
    from app.strategies.intra import run_intra
    from app.strategies.virada_tarde import ViradaTarde
    # 24 velas calmas e uma última com o fecho pedido; a entrada (vela seguinte) começa em hora_entrada:00 BRT
    from datetime import datetime
    from app.research.moratz.base import BRT
    entrada = int(datetime(2026, 11, 11, hora_entrada, 0, tzinfo=BRT).timestamp())
    inicio = entrada - 25 * 60
    calmas = [(1.0, 1.001, 0.999, 1.0003)] * 24
    o, lo, h = 1.0, 0.999, 1.002
    c = lo + fecho_alvo * (h - lo)
    velas = seq(*calmas, (o, h, lo, c), start_ts=inicio)
    s = ViradaTarde()
    s.bind_asset(par)
    return run_intra(velas, [s])[1][-1]


def test_virada_da_tarde_arma_put_no_topo_e_call_no_fundo_so_no_horario():
    from app.strategies.base import Direction
    from app.strategies.intra import INTRA_NAMES, OBSERVE_ONLY
    assert "virada_tarde" in INTRA_NAMES and "virada_tarde" not in OBSERVE_ONLY
    p = _plano_virada(0.95, 18)
    assert len(p.armed) == 1 and p.armed[0].direction is Direction.PUT and p.armed[0].touch_tol == 1e9
    assert p.armed[0].setup_label.startswith("Virada da Tarde")
    assert _plano_virada(0.05, 19).armed[0].direction is Direction.CALL  # 19h BRT = 17h NY em novembro
    assert _plano_virada(0.5, 18).armed == []           # fechou no meio
    assert _plano_virada(0.95, 17).armed == []          # 15h em NY: antes da janela
    assert _plano_virada(0.95, 20).armed == []          # 18h em NY: depois da janela
    assert _plano_virada(0.95, 18, par="EURUSD-OTC").armed == []  # nunca no OTC


def test_virada_da_tarde_bate_com_a_regra_do_laboratorio():
    """Nas mesmas velas, o bot arma exatamente onde as regras M-001 e M-002 disparam."""
    from app.strategies.intra import run_intra
    from app.strategies.virada_tarde import ViradaTarde
    from app.research.moratz.regra import ler
    from pathlib import Path
    velas = random_walk(3000, seed=21)
    velas = [type(v)(ts=BASE_TS + 60 * i, open=v.open, high=v.high, low=v.low, close=v.close) for i, v in enumerate(velas)]
    regras = Path(__file__).resolve().parents[2] / "docs" / "padrao_moratz" / "regras"
    t = tracos(serie(velas))
    esperado = {}
    for nome, d in (("M-001", "put"), ("M-002", "call")):
        r = ler(regras / f"{nome}.json")
        r["condicoes"] = [c for c in r["condicoes"] if c["traco"] != "hora"]  # o bot segue NY; aqui só o fecho
        dispara, _ = aplicar(r, t)
        for k in np.flatnonzero(dispara):
            esperado[int(BASE_TS + 60 * k)] = d
    s = ViradaTarde(horas_ny=None)
    s.bind_asset("EURUSD-op")
    armou = {int(p.armed[0].decision_ts): p.armed[0].direction.value for p in run_intra(velas, [s])[1] if p.armed}
    assert esperado and armou == esperado


def test_janela_de_ny_anda_com_o_horario_de_verao():
    from datetime import datetime
    from app.research.moratz.base import BRT
    from app.strategies.horario_ny import hora_ny
    assert hora_ny(int(datetime(2026, 10, 15, 18, 0, tzinfo=BRT).timestamp())) == 17  # outubro: 18h BRT = 17h NY
    assert hora_ny(int(datetime(2026, 11, 11, 19, 0, tzinfo=BRT).timestamp())) == 17  # novembro: 19h BRT = 17h NY


def test_bollinger_ny_so_arma_na_hora_do_fechamento_de_ny():
    from datetime import datetime
    from app.research.moratz.base import BRT
    from app.strategies.bb_rci import BollingerRci
    from app.strategies.bb_rci_ny import BollingerRciNY
    from app.strategies.horario_ny import hora_ny
    from app.strategies.intra import OBSERVE_ONLY, run_intra
    assert "bb_rci_ny" not in OBSERVE_ONLY
    inicio = int(datetime(2026, 11, 9, 0, 0, tzinfo=BRT).timestamp())
    velas = [type(v)(ts=inicio + 60 * i, open=v.open, high=v.high, low=v.low, close=v.close)
             for i, v in enumerate(random_walk(1440, seed=3))]
    base = {p.armed[0].target_ts for p in run_intra(velas, [BollingerRci()])[1] if p.armed}
    ny = BollingerRciNY()
    ny.bind_asset("EURUSD-op")
    armou = [p.armed[0] for p in run_intra(velas, [ny])[1] if p.armed]
    assert armou and {a.target_ts for a in armou} == {t for t in base if hora_ny(t) == 17}
    assert all(a.strategy == "bb_rci_ny" for a in armou)
    otc = BollingerRciNY()
    otc.bind_asset("EURUSD-OTC")
    assert not any(p.armed for p in run_intra(velas, [otc])[1])
