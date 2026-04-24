"""Package CLI entry points."""

from __future__ import annotations


def main() -> int:
    """Run the bundled FastMCP server."""
    from .server import mcp

    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
