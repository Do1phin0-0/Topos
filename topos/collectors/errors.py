"""Failures that mean "the source is not going to answer", not "bug".

Kept separate from ordinary HTTP errors because the response differs in
kind. A 500 is worth a retry; a feed that has been withdrawn or is
refusing this client will return the same thing forever, and presenting
that as a transient error sends you round a loop that cannot terminate.

History worth keeping: this project's congressional data originally came
from the House and Senate Stock Watcher S3 mirrors, which in August 2026
began returning AccessDenied to everyone. That is why collection now goes
to the House Clerk directly and parses PDFs — the structured mirror that
made it unnecessary no longer exists.
"""


class UpstreamUnavailable(RuntimeError):
    """A data source is refusing or no longer serving us its data."""
