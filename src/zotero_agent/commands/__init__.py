"""Command implementations. Each cmd_* takes the parsed argparse Namespace.

Commands return normally on success and raise term.ZotError on failure, so the
same functions back both the CLI (cli.py) and the MCP server (mcp_server.py).
"""
