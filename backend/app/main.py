"""Servidor do painel. Rode dentro de backend/:

    .venv/bin/python -m uvicorn app.main:app --port 8000 --timeout-graceful-shutdown 5

e abra http://127.0.0.1:8000 no navegador do Windows.
"""

import logging

from app.api.factory import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app(hard_exit=True)
