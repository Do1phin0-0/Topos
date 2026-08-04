import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from topos.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Topos signal pipeline.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Submit real paper-trading orders instead of a dry run.",
    )
    args = parser.parse_args()
    run(dry_run=not args.execute)


if __name__ == "__main__":
    main()
