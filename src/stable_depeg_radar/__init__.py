"""stable-depeg-radar — multichain stablecoin depeg early-warning radar.

Public surface:
    - :class:`tokens.TokenSpec`, :data:`tokens.KNOWN_STABLES`, :func:`tokens.lookup_token`
    - :class:`detector.Observation`, :class:`detector.DepegSignal`,
      :func:`detector.detect_depegs`
    - :class:`chainstream.ChainStreamClient`, :class:`chainstream.ChainStreamError`
    - :func:`format.format_pretty`, :func:`format.format_json`
    - :func:`cli.main`
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
