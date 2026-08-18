"""Operational failures should say what is wrong in one line.

A blocked port, a stopped database, and a wrong password all arrive as
the same SQLAlchemy exception wrapped in ~200 frames of connection-pool
internals. They have different fixes, so the message has to tell them
apart — and it must never print the password while doing it.
"""

import pytest
import requests
from sqlalchemy.exc import OperationalError

from topos.collectors.errors import UpstreamUnavailable
from topos.collectors.house_clerk import HouseClerkCollector
from topos.db.session import _describe


def _operational(message: str) -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception(message))


def test_timeout_is_reported_as_a_blocked_path_not_a_credential_problem():
    text = _describe(_operational("connection to server ... failed: Connection timed out"))

    assert "blocked path" in text
    assert "not a wrong password" in text
    # The reachability check is the actual next step, so it is in the message.
    assert "Test-NetConnection" in text


def test_refused_is_reported_as_nothing_listening():
    text = _describe(_operational("connection refused"))

    assert "refused the connection" in text
    assert "nothing is listening" in text
    assert "blocked path" not in text


def test_authentication_failure_is_not_confused_with_unreachability():
    text = _describe(_operational('password authentication failed for user "topos"'))

    assert "rejected the credentials" in text


def test_missing_database_is_distinguished_from_a_missing_host():
    text = _describe(_operational('database "topos" does not exist'))

    assert "not there" in text


def test_the_password_is_never_printed(monkeypatch):
    # This message is what gets pasted into chat when something breaks.
    text = _describe(_operational("connection timed out"))

    assert "***" in text
    assert "topos:topos@" not in text


# --- an upstream that refuses us --------------------------------------


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.content = b""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")


class _Session:
    def __init__(self, status_code: int):
        self.headers: dict[str, str] = {}
        self._status = status_code

    def get(self, url, timeout=0):
        return _Response(self._status)


def test_being_blocked_points_at_the_user_agent_not_at_retrying(tmp_path):
    # Public .gov archives need no credentials, so a 403 means this client
    # was filtered — a fact no amount of retrying changes.
    collector = HouseClerkCollector(cache_dir=tmp_path, delay=0, session=_Session(403))

    with pytest.raises(UpstreamUnavailable) as caught:
        collector.index(2024)

    assert "SEC_EDGAR_USER_AGENT" in str(caught.value)


def test_a_year_that_is_not_published_is_reported_as_such(tmp_path):
    collector = HouseClerkCollector(cache_dir=tmp_path, delay=0, session=_Session(404))

    with pytest.raises(UpstreamUnavailable, match="Not published"):
        collector.index(2099)


def test_ordinary_server_errors_still_raise_normally(tmp_path):
    # A 500 really might be transient — it must not be relabelled as a
    # source that will never answer.
    collector = HouseClerkCollector(cache_dir=tmp_path, delay=0, session=_Session(500))

    with pytest.raises(requests.HTTPError):
        collector.index(2024)
