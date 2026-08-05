"""Sentiment signals must be dated by their freshest underlying item.

Before this, all three sentiment sources stamped `datetime.now()` even
though the article/post/tweet timestamps were available (or requestable).
Two consequences that both corrupt validation: a week-old sentiment
reading claimed a forward return starting today, and re-scanning an
unchanged set of articles recorded a brand-new signal every single day,
inflating the ticker's signal count.
"""

from datetime import date, datetime, timezone

from topos.signals.news import NewsSignalExtractor
from topos.signals.reddit import RedditSignalExtractor
from topos.signals.timestamps import (
    latest_date,
    parse_epoch,
    parse_iso8601,
    parse_rfc2822,
)
from topos.signals.twitter import TwitterSignalExtractor

_POSITIVE = "Company smashes earnings expectations, stock soars on record profit"
_ALSO_POSITIVE = "Analysts upgrade rating after blockbuster quarter"


def test_parse_rfc2822_handles_rss_dates():
    parsed = parse_rfc2822("Mon, 05 Aug 2026 14:31:02 GMT")

    assert parsed.date() == date(2026, 8, 5)
    assert parse_rfc2822("not a date") is None
    assert parse_rfc2822(None) is None
    assert parse_rfc2822("") is None


def test_parse_epoch_handles_reddit_timestamps():
    parsed = parse_epoch(1785938400.0)  # 2026-08-05 UTC

    assert parsed.tzinfo is not None
    assert parse_epoch(None) is None
    assert parse_epoch("garbage") is None
    # A bool is an int subclass in Python; it must not parse as a time.
    assert parse_epoch(True) is None


def test_parse_iso8601_handles_x_timestamps():
    parsed = parse_iso8601("2026-08-05T14:31:02.000Z")

    assert parsed.date() == date(2026, 8, 5)
    assert parse_iso8601("nope") is None
    assert parse_iso8601(None) is None


def test_latest_date_picks_the_freshest_and_ignores_unparseable():
    stamps = [
        datetime(2026, 7, 1, tzinfo=timezone.utc),
        None,
        datetime(2026, 7, 20, tzinfo=timezone.utc),
        datetime(2026, 7, 5, tzinfo=timezone.utc),
    ]

    assert latest_date(stamps) == date(2026, 7, 20)
    assert latest_date([None, None]) is None
    assert latest_date([]) is None


def test_news_is_dated_by_freshest_article_not_today():
    headlines = [
        {"title": _POSITIVE, "pub_date": "Wed, 15 Jul 2026 10:00:00 GMT"},
        {"title": _ALSO_POSITIVE, "pub_date": "Fri, 17 Jul 2026 10:00:00 GMT"},
    ]

    signal = NewsSignalExtractor()._score("ACME", headlines)

    assert signal.event_date == date(2026, 7, 17)
    assert signal.event_date != datetime.now(timezone.utc).date()
    assert signal.evidence["latest_article_date"] == "2026-07-17"


def test_rescanning_unchanged_articles_produces_the_same_dedup_key():
    # The whole point: stale coverage must not be re-recorded as a fresh
    # signal on every scheduled run.
    headlines = [{"title": _POSITIVE, "pub_date": "Wed, 15 Jul 2026 10:00:00 GMT"}]

    first = NewsSignalExtractor()._score("ACME", headlines)
    later = NewsSignalExtractor()._score("ACME", headlines)

    assert first.dedup_key == later.dedup_key


def test_a_newer_article_produces_a_new_dedup_key():
    old = [{"title": _POSITIVE, "pub_date": "Wed, 15 Jul 2026 10:00:00 GMT"}]
    fresh = old + [{"title": _ALSO_POSITIVE, "pub_date": "Mon, 20 Jul 2026 10:00:00 GMT"}]

    assert (
        NewsSignalExtractor()._score("ACME", old).dedup_key
        != NewsSignalExtractor()._score("ACME", fresh).dedup_key
    )


def test_news_is_dropped_when_no_article_can_be_dated():
    headlines = [{"title": _POSITIVE, "pub_date": "unparseable"}]

    assert NewsSignalExtractor()._score("ACME", headlines) is None


def test_reddit_is_dated_by_newest_post():
    posts = [
        {"title": _POSITIVE, "selftext": "", "score": 10, "created_utc": 1784131200.0},
        {"title": _ALSO_POSITIVE, "selftext": "", "score": 5, "created_utc": 1784304000.0},
    ]

    signal = RedditSignalExtractor()._score("ACME", posts)

    assert signal.event_date == max(
        parse_epoch(p["created_utc"]).date() for p in posts
    )
    assert signal.evidence["latest_post_date"] == signal.event_date.isoformat()


def test_reddit_is_dropped_when_posts_carry_no_timestamps():
    posts = [{"title": _POSITIVE, "selftext": "", "score": 10}]

    assert RedditSignalExtractor()._score("ACME", posts) is None


def test_twitter_is_dated_by_newest_tweet():
    tweets = [
        {"text": _POSITIVE, "created_at": "2026-07-15T10:00:00.000Z"},
        {"text": _ALSO_POSITIVE, "created_at": "2026-07-18T10:00:00.000Z"},
    ]

    signal = TwitterSignalExtractor()._score("ACME", tweets)

    assert signal.event_date == date(2026, 7, 18)
    assert signal.evidence["latest_tweet_date"] == "2026-07-18"


def test_twitter_is_dropped_when_tweets_carry_no_timestamps():
    # X omits created_at unless tweet.fields requests it; if that request
    # ever regresses, the signal must fail loudly rather than silently
    # backdating everything to today.
    tweets = [{"text": _POSITIVE}]

    assert TwitterSignalExtractor()._score("ACME", tweets) is None


def test_twitter_collector_requests_created_at():
    from unittest.mock import MagicMock, patch

    from topos.collectors.twitter import TwitterCollector

    collector = TwitterCollector()
    collector._bearer_token = "test-token"

    response = MagicMock()
    response.json.return_value = {"data": []}
    response.raise_for_status = lambda: None

    with patch("topos.collectors.twitter.requests.get", return_value=response) as mock_get:
        collector.search_recent("$ACME")

    assert mock_get.call_args.kwargs["params"]["tweet.fields"] == "created_at"
