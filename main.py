"""Main entry point for res-ops-mcp."""

from res_ops.server import mcp


def main():
    """Run the MCP server."""
    print("Starting res-ops-mcp MCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
