"""Confere a sintaxe do JavaScript do painel (sem navegador). Pula se o esprima não estiver instalado."""

import pytest

from app.api.factory import FRONTEND_DIR


def test_app_js_tem_sintaxe_valida():
    esprima = pytest.importorskip("esprima")
    code = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    esprima.parseScript(code)


def test_index_referencia_os_arquivos():
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    for needed in ('src="app.js"', 'href="style.css"', "lightweight-charts@4.2.0"):
        assert needed in html
