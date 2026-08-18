from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import topos.collectors.cusip_resolver as cusip_resolver_module
from topos.collectors.cusip_resolver import CusipResolver
from topos.db.models import Base, CusipTickerCache


def _patched_resolver(monkeypatch, query_impl):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(cusip_resolver_module, "SessionLocal", session_factory)

    resolver = CusipResolver()
    calls = []

    def fake_query(cusips):
        calls.append(list(cusips))
        return query_impl(cusips)

    monkeypatch.setattr(resolver, "_query_openfigi", fake_query)
    return resolver, calls, session_factory


def test_resolve_many_caches_results_across_calls(monkeypatch):
    resolver, calls, session_factory = _patched_resolver(
        monkeypatch, lambda cusips: {c: f"TICK-{c}" for c in cusips}
    )

    first = resolver.resolve_many(["AAA111111"])
    second = resolver.resolve_many(["AAA111111"])

    assert first == {"AAA111111": "TICK-AAA111111"}
    assert second == first
    assert len(calls) == 1  # second call hit the cache, no new API call

    session = session_factory()
    assert session.query(CusipTickerCache).count() == 1


def test_resolve_many_caches_unresolvable_cusips_too(monkeypatch):
    resolver, calls, _ = _patched_resolver(monkeypatch, lambda cusips: {})

    first = resolver.resolve_many(["BBB222222"])
    second = resolver.resolve_many(["BBB222222"])

    assert first == {"BBB222222": None}
    assert second == {"BBB222222": None}
    assert len(calls) == 1
