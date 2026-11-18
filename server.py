"""Hosted entrypoint: server.py:mcp"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_eu_funding.server import mcp  # noqa: E402,F401
