#!/usr/bin/env bash
# Sobe o servidor do BotBene. Chamado pelo atalho do Windows (BotBene.ps1). Log em data/server.log.
# Código 75 = o próprio servidor pediu para reiniciar (app/service/guard.py): sobe de novo e ele retoma o bot.
# Qualquer outro código (inclusive "Desligar BotBene") encerra de verdade.
cd "$(dirname "$0")/../backend" || exit 1
mkdir -p ../data
export BOTBENE_SUPERVISED=1
while true; do
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 >> ../data/server.log 2>&1
    code=$?
    [ "$code" -eq 75 ] || exit "$code"
    sleep 2
done
