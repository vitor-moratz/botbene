from __future__ import annotations

from collections.abc import Callable

from app.broker.base import AccountType, Broker
from app.config import Settings
from app.service.config_store import ConfigStore


def chosen_account(settings: Settings, config: ConfigStore | None) -> tuple[AccountType, bool]:
    """Conta escolhida e se a REAL está liberada. Sem a tela, vale o .env (IQ_ACCOUNT / IQ_ALLOW_REAL).
    Na tela, a REAL só fica escolhida depois da confirmação digitada (rota /api/account)."""
    if config is not None:
        account = AccountType(config.get().account)
        return account, settings.iq_allow_real or account is AccountType.REAL
    return AccountType(settings.iq_account.upper()), settings.iq_allow_real


def iq_broker_factory(settings: Settings, config: ConfigStore | None = None) -> Callable[[], Broker]:
    """Cria e conecta o adaptador da IQ Option. Login: o salvo na tela de Configuração; sem ele, o do .env."""

    def make() -> Broker:
        from app.broker.iqoption import IQOptionBroker

        email, password = config.credentials() if config is not None else (settings.iq_email, settings.iq_password)
        account, allow_real = chosen_account(settings, config)
        broker = IQOptionBroker(email, password, allow_real=allow_real)
        broker.connect()
        if account is not broker.account:
            broker.set_account(account)
        return broker

    return make
