import xml.etree.ElementTree as ET

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from topos.db.models import Base, Filing13FPosition
from topos.signals.filing_13f import Filing13FSignalExtractor, _parse_filer

_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _info_table_xml(holdings):
    """Builds a namespaced informationTable, matching real SEC 13F XML, to
    exercise the namespace-stripping the extractor depends on."""
    root = ET.Element(f"{{{_NS}}}informationTable")
    for h in holdings:
        entry = ET.SubElement(root, f"{{{_NS}}}infoTable")
        ET.SubElement(entry, f"{{{_NS}}}nameOfIssuer").text = h["name"]
        ET.SubElement(entry, f"{{{_NS}}}cusip").text = h["cusip"]
        ET.SubElement(entry, f"{{{_NS}}}value").text = str(h["value_thousands"])
        shrs = ET.SubElement(entry, f"{{{_NS}}}shrsOrPrnAmt")
        ET.SubElement(shrs, f"{{{_NS}}}sshPrnamt").text = str(h["shares"])
    return root


class _FakeCollector:
    def __init__(self, filings, docs_by_index, xml_by_url):
        self._filings = filings
        self._docs_by_index = docs_by_index
        self._xml_by_url = xml_by_url

    def latest_filings(self, form_type, count):
        return self._filings

    def filing_documents(self, index_url):
        return self._docs_by_index[index_url]

    def fetch_xml(self, url):
        return self._xml_by_url[url]


class _FakeResolver:
    def __init__(self, mapping):
        self._mapping = mapping

    def resolve_many(self, cusips):
        return {c: self._mapping.get(c) for c in cusips}


_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/1037389/000103738924000001-index.htm"
_INFO_URL = f"{_INDEX_URL.rsplit('/', 1)[0]}/infotable.xml"
_TITLE = "13F-HR - Renaissance Technologies LLC (0001037389) (Filer)"


def _extractor(holdings, resolver_mapping, filed_at="2024-08-14T16:30:00-04:00"):
    filings = [{"title": _TITLE, "index_url": _INDEX_URL, "filed_at": filed_at}]
    docs = {_INDEX_URL: [_INFO_URL]}
    xml = {_INFO_URL: _info_table_xml(holdings)}
    return Filing13FSignalExtractor(
        collector=_FakeCollector(filings, docs, xml),
        resolver=_FakeResolver(resolver_mapping),
    )


def test_parse_filer_from_atom_title():
    assert _parse_filer(_TITLE) == ("Renaissance Technologies LLC", "0001037389")
    assert _parse_filer("garbage") is None


def test_new_material_position_emits_buy_signal():
    holdings = [{"name": "Acme Corp", "cusip": "000000AA1", "value_thousands": 10_000, "shares": 1000}]
    session = _make_session()
    extractor = _extractor(holdings, {"000000AA1": "ACME"})

    signals = extractor.extract(session=session)

    assert len(signals) == 1
    assert signals[0].ticker == "ACME"
    assert signals[0].direction == "buy"
    assert signals[0].evidence["position_change"] == "new_position"
    assert session.query(Filing13FPosition).count() == 1


def test_tiny_new_position_is_ignored_as_noise():
    holdings = [{"name": "Acme Corp", "cusip": "000000AA1", "value_thousands": 10, "shares": 5}]
    session = _make_session()
    extractor = _extractor(holdings, {"000000AA1": "ACME"})

    signals = extractor.extract(session=session)

    assert signals == []
    # still recorded, so a future increase can be diffed correctly
    assert session.query(Filing13FPosition).count() == 1


def test_same_quarter_refetch_does_not_reemit_signal():
    holdings = [{"name": "Acme Corp", "cusip": "000000AA1", "value_thousands": 10_000, "shares": 1000}]
    session = _make_session()
    extractor = _extractor(holdings, {"000000AA1": "ACME"})

    first = extractor.extract(session=session)
    second = extractor.extract(session=session)

    assert len(first) == 1
    assert second == []


def test_material_increase_emits_buy_signal_next_quarter():
    session = _make_session()
    session.add(
        Filing13FPosition(
            cik="0001037389",
            filer_name="Renaissance Technologies LLC",
            cusip="000000AA1",
            name_of_issuer="Acme Corp",
            filed_at="2024-05-14T16:30:00-04:00",
            shares=1000,
            value_usd=10_000_000,
        )
    )
    session.commit()

    holdings = [{"name": "Acme Corp", "cusip": "000000AA1", "value_thousands": 15_000, "shares": 1500}]
    extractor = _extractor(holdings, {"000000AA1": "ACME"})

    signals = extractor.extract(session=session)

    assert len(signals) == 1
    assert signals[0].direction == "buy"
    assert signals[0].evidence["position_change"] == "increased"


def test_full_exit_emits_sell_signal():
    session = _make_session()
    session.add(
        Filing13FPosition(
            cik="0001037389",
            filer_name="Renaissance Technologies LLC",
            cusip="000000AA1",
            name_of_issuer="Acme Corp",
            filed_at="2024-05-14T16:30:00-04:00",
            shares=1000,
            value_usd=10_000_000,
        )
    )
    session.commit()

    extractor = _extractor([], {"000000AA1": "ACME"})  # holding no longer in the new filing

    signals = extractor.extract(session=session)

    assert len(signals) == 1
    assert signals[0].direction == "sell"
    assert signals[0].evidence["position_change"] == "closed_position"
    assert session.query(Filing13FPosition).count() == 0


def test_unresolvable_cusip_is_dropped_not_surfaced():
    holdings = [{"name": "Acme Corp", "cusip": "000000AA1", "value_thousands": 10_000, "shares": 1000}]
    session = _make_session()
    extractor = _extractor(holdings, {})  # resolver can't map this CUSIP

    signals = extractor.extract(session=session)

    assert signals == []
