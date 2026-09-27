"""Allow running growthhat as a module: python -m growthhat"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
