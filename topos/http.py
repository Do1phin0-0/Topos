import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(
    total_retries: int = 3,
    backoff_factor: float = 0.5,
    methods: tuple[str, ...] = ("GET",),
) -> requests.Session:
    """A requests.Session with retry/backoff for transient network errors
    and 429/5xx responses. Collectors run unattended on an hourly cron, so
    a single flaky response from SEC EDGAR or the stock-watcher mirrors
    shouldn't fail the whole pipeline run. GET-only by default: never pass
    POST here for order placement, where a retried request could
    double-submit. POST is safe to include for read-only/idempotent
    lookups (e.g. a CUSIP->ticker mapping call) that have no side effects."""
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=methods,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
