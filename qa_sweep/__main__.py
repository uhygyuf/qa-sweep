"""Allow python -m qa_sweep."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
