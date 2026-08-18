"""Shared entry point for the command-line scripts.

Operational failures — an unreachable database, a retired upstream feed —
are not bugs, and printing a hundred frames of library internals for them
buries the one line that says what to do. These get a plain message and a
non-zero exit; anything unexpected still raises with its full traceback,
because that one really is a bug and the frames are the evidence.
"""

import sys
from typing import Callable

from topos.collectors.errors import UpstreamUnavailable
from topos.db.session import DatabaseUnreachable


def run(main: Callable[[], None]) -> None:
    try:
        main()
    except (DatabaseUnreachable, UpstreamUnavailable) as error:
        print(f"\n{error}\n", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
