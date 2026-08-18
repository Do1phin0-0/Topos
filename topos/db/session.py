from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from topos.config import load_settings
from topos.db.models import Base

settings = load_settings()

# psycopg2 has no default connect timeout, so an unreachable host makes
# every script hang on the OS TCP timeout — minutes of a dead terminal
# before the traceback. Fail fast enough to be diagnosable, slow enough
# to survive an ordinary slow handshake to a remote region.
_connect_args = (
    {"connect_timeout": 15} if settings.database_url.startswith("postgresql") else {}
)
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class DatabaseUnreachable(RuntimeError):
    """The database could not be reached — as distinct from a bug in a query.

    Raised instead of letting SQLAlchemy's connection-pool traceback
    surface, because that traceback is ~200 lines of internal frames whose
    one useful line is buried at the bottom, and it looks like the code
    broke when nothing did.
    """


def _describe(error: Exception) -> str:
    host = engine.url.host or "the configured host"
    detail = str(error.__cause__ or error).strip().splitlines()
    first = detail[0] if detail else str(error)

    # "timed out" means packets left and nothing came back — something in
    # the path is dropping them silently. "refused" means a machine
    # answered and said no. They point at different fixes, so name them.
    if "timeout" in first.lower() or "timed out" in first.lower():
        hint = (
            f"Nothing answered at {host}:{engine.url.port or 5432} before the timeout.\n"
            "  That is a blocked path, not a wrong password — traffic is being\n"
            "  dropped in transit. Common causes: a VPN or network filter that\n"
            "  blocks outbound 5432, or a database access-control list that does\n"
            "  not include your current IP address.\n"
            "  Check reachability first:\n"
            f"    Test-NetConnection {host} -Port {engine.url.port or 5432}    (Windows)\n"
            f"    nc -vz {host} {engine.url.port or 5432}                      (macOS/Linux)"
        )
    elif "refused" in first.lower():
        hint = (
            f"{host}:{engine.url.port or 5432} refused the connection.\n"
            "  The host is reachable but nothing is listening on that port — the\n"
            "  database is stopped, or DATABASE_URL names the wrong port."
        )
    elif "password" in first.lower() or "authentication" in first.lower():
        hint = "The host answered but rejected the credentials in DATABASE_URL."
    elif "does not exist" in first.lower():
        hint = "The host answered, but the database named in DATABASE_URL is not there."
    else:
        hint = first

    return (
        f"Cannot reach the database.\n\n  {hint}\n\n"
        f"  DATABASE_URL currently points at: {engine.url.render_as_string(hide_password=True)}"
    )


def init_db() -> None:
    try:
        Base.metadata.create_all(engine)
    except OperationalError as error:
        raise DatabaseUnreachable(_describe(error)) from error
