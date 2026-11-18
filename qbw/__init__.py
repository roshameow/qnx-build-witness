"""Source-checkout import shim.

The maintained package lives in ``src/qbw``. This tiny shim lets a developer run
``python3 -m qbw ...`` from the repository root without installing first. It is
not part of the installed distribution (setuptools discovers only ``src``).
"""

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "qbw"
if str(_SRC_PACKAGE) not in __path__:
    __path__.append(str(_SRC_PACKAGE))

from .version import __version__  # noqa: E402

__all__ = ["__version__"]
