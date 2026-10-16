from __future__ import annotations


def _patch_aiomysql_bytes_escape() -> None:
    """Use PyMySQL's current bytes encoder when its legacy alias is not callable."""
    try:
        import aiomysql.connection as aiomysql_connection
        from pymysql.converters import escape_bytes
    except ImportError:
        return

    if not callable(aiomysql_connection.escape_bytes_prefixed):
        aiomysql_connection.escape_bytes_prefixed = escape_bytes


_patch_aiomysql_bytes_escape()
