#!/usr/bin/env python3
"""Legacy destructive reset is disabled to prevent accidental document deletion."""

import sys


def main() -> int:
    print(
        "Database reset is disabled. This command will not delete or modify MongoDB "
        "documents or any legacy MySQL data. Use a separately reviewed, explicitly "
        "approved maintenance procedure if a reset is required.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
