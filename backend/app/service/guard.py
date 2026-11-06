"""Último recurso do vigia: reinicia o servidor inteiro quando a reconexão não resolve.

O bot já reconecta sozinho e as threads presas da biblioteca são encerradas no prazo. Sobram os casos
sem saída dentro do processo: chamadas presas na rede que não encerram, ou a IQ sem responder a várias
tentativas seguidas de login. Aí o guarda grava como retomar a sessão e sai com o código RESTART_CODE;
quem sobe o servidor (desktop/start_server.sh) abre outro processo, que retoma o bot sozinho.

Só roda com BOTBENE_SUPERVISED=1: sem o script em volta, sair seria só derrubar o servidor.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.broker.iqoption import MAX_STUCK_CALLS, stuck_calls
from app.service.bot import BotService

log = logging.getLogger(__name__)

RESTART_CODE = 75
HUNG_ATTEMPTS_LIMIT = 4  # tentativas seguidas de reconectar em que a IQ nem respondeu
ORDER_WAIT_SECONDS = 100  # espera as ordens abertas fecharem (1 min + a folga do resultado)
MIN_RESTART_GAP = 900  # nunca reinicia mais de uma vez em 15 min (ex.: a própria IQ fora do ar)
RESUME_MAX_AGE = 600  # o aviso de retomada vale por 10 min
CHECK_SECONDS = 10


class ProcessGuard:
    def __init__(self, bot: BotService, data_dir: Path, stuck: Callable[[], int] = stuck_calls,
                 exit_fn: Callable[[int], None] = os._exit) -> None:
        self.bot = bot
        self.resume_path = data_dir / "retomar.json"
        self.stamp_path = data_dir / "ultimo_reinicio"
        self._stuck, self._exit = stuck, exit_fn
        self._stop = threading.Event()
        self._waiting_since: float | None = None

    def start(self) -> None:
        threading.Thread(target=self._loop, name="guarda-processo", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_SECONDS):
            try:
                self.check()
            except Exception:  # noqa: BLE001 - o guarda nunca pode cair
                log.exception("Guarda do processo")

    def _problem(self) -> str | None:
        stuck = self._stuck()
        if stuck >= MAX_STUCK_CALLS:
            return f"{stuck} chamadas à IQ presas"
        if self.bot.hung_attempts >= HUNG_ATTEMPTS_LIMIT:
            return f"a IQ não respondeu a {self.bot.hung_attempts} tentativas seguidas de login"
        return None

    def check(self) -> None:
        why = self._problem()
        if why is None:
            self._waiting_since = None
            return
        if self._restarted_recently():
            return
        now = time.time()
        self._waiting_since = self._waiting_since or now
        if self.bot.orders.open_count and now - self._waiting_since < ORDER_WAIT_SECONDS:
            return  # o resultado de uma ordem aberta ainda pode chegar
        self.restart(why)

    def _restarted_recently(self) -> bool:
        try:
            return time.time() - self.stamp_path.stat().st_mtime < MIN_RESTART_GAP
        except OSError:
            return False

    def restart(self, why: str) -> None:
        log.error("Reiniciando o servidor: %s", why)
        self.stamp_path.touch()
        self.resume_path.write_text(json.dumps(self.bot.resume_info(why), ensure_ascii=False), encoding="utf-8")
        self._exit(RESTART_CODE)

    def take_resume(self) -> dict | None:
        """Ao subir: há sessão para retomar? O aviso é usado uma vez só (e apagado)."""
        try:
            info = json.loads(self.resume_path.read_text(encoding="utf-8"))
            self.resume_path.unlink()
        except (OSError, ValueError):
            return None
        if not info.get("resume") or time.time() - float(info.get("at") or 0) > RESUME_MAX_AGE:
            return None
        return info
