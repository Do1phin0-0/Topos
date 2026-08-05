import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.db.session import init_db


def main() -> None:
    init_db()
    print("Database initialized.")


if __name__ == "__main__":
    from _cli import run

    run(main)
