"""Operational failures should say what is wrong in one line.

A blocked port, a stopped database, and a wrong password all arrive as
the same SQLAlchemy exception wrapped in ~200 frames of connection-pool
internals. They have different fixes, so the message has to tell them
apart — and it must never print the password while doing it.
"""

import pytest
import requests
from sqlalchemy.exc import OperationalError

from topos.collectors.congress import CongressTradeCollector, UpstreamUnavailable
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


# --- withdrawn upstream feed -----------------------------------------


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        raise requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return []


def test_a_withdrawn_feed_says_so_instead_of_looking_like_a_blip(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(403))

    with pytest.raises(UpstreamUnavailable) as caught:
        CongressTradeCollector().house_transactions()

    message = str(caught.value)
    assert "withdrawn" in message
    # Retrying is the natural reaction to a 403 and it is the wrong one.
    assert "retrying will not help" in message
    assert "other collectors are unaffected" in message


def test_ordinary_server_errors_still_raise_normally(monkeypatch):
    # A 500 really might be transient — it must not be relabelled as a
    # permanently withdrawn feed.
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(500))

    with pytest.raises(requests.HTTPError):
        CongressTradeCollector().house_transactions()
