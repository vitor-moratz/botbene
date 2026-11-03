from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.broker.base import AccountType
from app.broker.iqoption import IQOptionBroker
from app.config import get_settings

BRT = ZoneInfo("America/Sao_Paulo")


def setup_logging() -> None:
    # force=True: a biblioteca da IQ mexe no logging ao ser importada; sem isso nossas mensagens somem.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)


def make_broker() -> IQOptionBroker:
    s = get_settings()
    broker = IQOptionBroker(
        s.iq_email,
        s.iq_password,
        allow_real=s.iq_allow_real,
        sms_code_provider=lambda: input("Código SMS da IQ Option: ").strip(),
    )
    broker.connect()
    account = AccountType(s.iq_account.upper())
    if account is not broker.account:
        broker.set_account(account)
    return broker


def fmt_time(ts: int) -> tuple[str, str]:
    """(UTC, horário de Brasília) de um timestamp."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M"), dt.astimezone(BRT).strftime("%Y-%m-%d %H:%M")
