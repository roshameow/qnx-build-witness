"""QNX Build Witness (QBW).

QBW is a host-side CLI that records real build, boot, and target-test commands
as a verifiable evidence package. It never creates QNX evidence by itself.
"""

from .version import __version__

__all__ = ["__version__"]
