"""Allow ``python -m qbw`` from a source checkout."""

from .cli import main

raise SystemExit(main())
