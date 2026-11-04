"""Data e hora do NEGÓCIO (fuso do cliente), não do servidor.

O servidor roda em UTC; o cliente, a cotação do Banco Central e a previsão do tempo vivem no fuso do Brasil. Entre
00h e 03h UTC o "hoje" do servidor já é o "amanhã" do cliente: medido, a previsão de amanhã para Porto Alegre (data
local certa) saiu recusada porque o prompt dizia que hoje era o dia da previsão. Todo "hoje" do sistema (prompt,
checagem de datas, dado ao vivo e as tools do domínio) vem daqui. APP_TZ troca o fuso (nome IANA).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "America/Sao_Paulo"


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("APP_TZ") or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):  # nome inválido no ambiente: o fuso padrão, nunca o do servidor
        return ZoneInfo(DEFAULT_TZ)


def now() -> datetime:
    """Agora no fuso do negócio, sem tzinfo (o mesmo formato que as tools já gravavam)."""
    return datetime.now(tz()).replace(tzinfo=None)


def today() -> date:
    return datetime.now(tz()).date()
