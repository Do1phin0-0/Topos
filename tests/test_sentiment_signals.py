from topos.collectors.reddit import RedditCollector
from topos.collectors.twitter import TwitterCollector
from topos.signals.news import NewsSignalExtractor
from topos.signals.reddit import RedditSignalExtractor
from topos.signals.twitter import TwitterSignalExtractor


def test_news_sentiment_positive_headlines_score_buy():
    headlines = [
        {"title": "Company smashes earnings expectations, stock soars on record profit"},
        {"title": "Analysts upgrade rating after blockbuster quarter"},
    ]

    signal = NewsSignalExtractor()._score("TEST", headlines)

    assert signal.evidence["direction"] == "buy"


def test_news_sentiment_negative_headlines_score_sell():
    headlines = [
        {"title": "Company misses earnings badly, stock plunges on huge losses"},
        {"title": "Regulators fine firm amid fraud investigation scandal"},
    ]

    signal = NewsSignalExtractor()._score("TEST", headlines)

    assert signal.evidence["direction"] == "sell"


def test_news_sentiment_neutral_headlines_produce_no_signal():
    headlines = [{"title": "Company to hold quarterly meeting on Tuesday"}]

    assert NewsSignalExtractor()._score("TEST", headlines) is None


def test_news_sentiment_empty_headlines_produce_no_signal():
    assert NewsSignalExtractor()._score("TEST", []) is None


def test_reddit_and_twitter_disabled_without_credentials():
    assert RedditCollector().enabled is False
    assert TwitterCollector().enabled is False
    assert RedditSignalExtractor().extract(["AAPL"]) == []
    assert TwitterSignalExtractor().extract(["AAPL"]) == []
