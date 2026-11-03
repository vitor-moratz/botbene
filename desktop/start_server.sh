#!/usr/bin/env bash
# Sobe o servidor do BotBene. Chamado pelo atalho do Windows (BotBene.ps1).
# Log em data/server.log.
set -e
cd "$(dirname "$0")/../backend"
mkdir -p ../data
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> ../data/server.log 2>&1
