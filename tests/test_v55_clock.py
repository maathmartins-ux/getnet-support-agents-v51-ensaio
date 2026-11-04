"""v5.5.1: o "hoje" do sistema é o do negócio (fuso do cliente), não o do servidor em UTC."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app import agents, clock


def test_business_clock_defaults_to_brazil_and_env_wins(monkeypatch):
    monkeypatch.delenv("APP_TZ", raising=False)
    assert clock.tz().key == "America/Sao_Paulo"
    monkeypatch.setenv("APP_TZ", "Asia/Tokyo")
    assert clock.tz().key == "Asia/Tokyo"
    monkeypatch.setenv("APP_TZ", "Nao/Existe")
    assert clock.tz().key == "America/Sao_Paulo"  # nome inválido: o padrão, nunca o fuso do servidor


def test_today_follows_the_business_zone_not_utc(monkeypatch):
    """Às 00h30 UTC de 4/11 ainda é 3/11 em São Paulo: o prompt e as tools usam 3/11."""
    fixed = datetime(2026, 11, 4, 0, 30, tzinfo=UTC)

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", FakeDT)
    monkeypatch.delenv("APP_TZ", raising=False)
    assert clock.today() == date(2026, 11, 3)
    assert agents._today().startswith("2026-11-03")
    monkeypatch.setenv("APP_TZ", "UTC")
    assert clock.today() == date(2026, 11, 4) and clock.today() - timedelta(days=1) == date(2026, 11, 3)
