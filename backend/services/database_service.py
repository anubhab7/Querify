"""
Database service for PostgreSQL operations.
Handles schema retrieval, query safety validation, and data sampling.
"""

import asyncpg
import re
from typing import List, Dict, Optional, Tuple
from sqlparse import parse, sql
import logging
import socket
import ssl as ssl_lib
from urllib.parse import quote

from asyncpg import exceptions as asyncpg_exceptions

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Structured database connection error."""

    def __init__(self, code: str, message: str, status_code: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DatabaseService:
    """Service for database operations with schema introspection and query validation."""

    def __init__(self, connection_string: str):
        """
        Initialize the database service.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool to PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.connection_string,
                min_size=1,
                max_size=5,
                timeout=10,
                command_timeout=10,
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            classified_error = self._classify_connection_error(e)
            logger.error(
                "Failed to create database connection pool [%s]: %s",
                classified_error.code,
                classified_error.message,
            )
            raise classified_error from e

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def test_connection(self) -> bool:
        """
        Test the database connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            if not self.pool:
                await self.connect()

            async with self.pool.acquire() as connection:
                result = await connection.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    @classmethod
    def build_connection_string(
        cls,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
    ) -> str:
        """Build a PostgreSQL connection string from discrete credentials."""
        quoted_username = quote(username, safe="")
        quoted_password = quote(password, safe="")
        quoted_host = host.strip()
        quoted_database = quote(database, safe="")
        return (
            f"postgresql://{quoted_username}:{quoted_password}"
            f"@{quoted_host}:{port}/{quoted_database}"
        )

    @classmethod
    async def test_credentials(
        cls,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ssl: Optional[bool] = None,
        ) -> None:
        """
        Validate a set of PostgreSQL credentials using a short-lived pool.

        Raises:
            DatabaseConnectionError: If the connection attempt fails
        """
        connection_string = cls.build_connection_string(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )

        pool: Optional[asyncpg.Pool] = None
        try:
            ssl_config = cls._build_ssl_config(ssl)
            pool = await asyncpg.create_pool(
                dsn=connection_string,
                min_size=1,
                max_size=1,
                timeout=10,
                command_timeout=10,
                ssl=ssl_config,
            )
            async with pool.acquire() as connection:
                await connection.fetchval("SELECT 1")
        except Exception as e:
            raise cls._classify_connection_error(e) from e
        finally:
            if pool:
                await pool.close()

    async def get_compact_database_schema(self) -> str:
        """
        Retrieve the database schema in compact format.

        Returns schema as: schema.table: col1, col2, col3

        Returns:
            Formatted schema string
        """
        if not self.pool:
            await self.connect()

        try:
            query = """
                SELECT 
                    t.table_schema,
                    t.table_name,
                    STRING_AGG(c.column_name, ', ' ORDER BY c.ordinal_position) as columns
                FROM 
                    information_schema.tables t
                    LEFT JOIN information_schema.columns c 
                    ON t.table_schema = c.table_schema 
                    AND t.table_name = c.table_name
                WHERE 
                    t.table_schema NOT IN ('pg_catalog', 'information_schema')
                GROUP BY 
                    t.table_schema, t.table_name
                ORDER BY 
                    t.table_schema, t.table_name;
            """

            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query)

            schema_lines = []
            for row in rows:
                schema_name = row["table_schema"]
                table_name = row["table_name"]
                columns = row["columns"] or ""
                schema_lines.append(f"{schema_name}.{table_name}: {columns}")

            return "\n".join(schema_lines)

        except Exception as e:
            logger.error(f"Error retrieving database schema: {e}")
            raise

    async def get_column_value_samples(
        self, schema: str, table: str, column: str, limit: int = 5
    ) -> List[str]:
        """
        Fetch distinct values from a column to help LLM with filtering.

        Args:
            schema: Schema name
            table: Table name
            column: Column name
            limit: Maximum number of samples to return (default 5)

        Returns:
            List of distinct values from the column
        """
        if not self.pool:
            await self.connect()

        try:
            # Validate identifiers to prevent SQL injection
            if not self._is_valid_identifier(schema) or not self._is_valid_identifier(
                table
            ):
                raise ValueError("Invalid schema or table name")

            if not self._is_valid_identifier(column):
                raise ValueError("Invalid column name")

            query = f"""
                SELECT DISTINCT {column}
                FROM {schema}.{table}
                WHERE {column} IS NOT NULL
                ORDER BY {column}
                LIMIT {limit};
            """

            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query)

            return [str(row[column]) for row in rows]

        except Exception as e:
            logger.error(
                f"Error retrieving column samples from {schema}.{table}.{column}: {e}"
            )
            return []

    async def is_safe_select_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a query is safe to execute (only SELECT and WITH statements).

        Strictly rejects queries containing INSERT, UPDATE, DELETE, DROP, ALTER, etc.

        Args:
            query: SQL query to validate

        Returns:
            Tuple of (is_safe: bool, error_message: Optional[str])
        """
        if not query or not query.strip():
            return False, "Query is empty"

        # Normalize query
        normalized_query = query.strip()

        # Check for dangerous keywords
        dangerous_patterns = [
            r"\bINSERT\b",
            r"\bUPDATE\b",
            r"\bDELETE\b",
            r"\bDROP\b",
            r"\bALTER\b",
            r"\bCREATE\b",
            r"\bTRUNCATE\b",
            r"\bGRANT\b",
            r"\bREVOKE\b",
            r"\bEXECUTE\b",
            r"\bEXEC\b",
            r"\bPRAGMA\b",
            r"\bCOMMIT\b",
            r"\bROLLBACK\b",
        ]

        # Compile regex patterns (case-insensitive)
        for pattern in dangerous_patterns:
            if re.search(pattern, normalized_query, re.IGNORECASE):
                return False, f"Query contains forbidden keyword: {pattern}"

        # Parse query to validate structure
        try:
            parsed = parse(normalized_query)

            if not parsed:
                return False, "Could not parse query"

            for statement in parsed:
                # Get the first token (should be SELECT or WITH)
                first_token = None
                for token in statement.tokens:
                    if not token.is_whitespace:
                        first_token = token
                        break

                if first_token is None:
                    return False, "Query has no valid tokens"

                token_type = first_token.ttype
                token_value = str(first_token).upper().strip()

                # Only allow SELECT and WITH statements
                if token_value not in ("SELECT", "WITH"):
                    return False, f"Only SELECT and WITH queries are allowed, got: {token_value}"

            return True, None

        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            return False, f"Could not parse query: {str(e)}"

    async def execute_select_query(self, query: str) -> List[Dict]:
        """
        Execute a validated SELECT query and return results.

        Args:
            query: SELECT query to execute

        Returns:
            List of dictionaries containing query results

        Raises:
            ValueError: If query is not safe
        """
        is_safe, error_msg = await self.is_safe_select_query(query)
        if not is_safe:
            raise ValueError(f"Unsafe query: {error_msg}")

        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise

    @staticmethod
    def _is_valid_identifier(identifier: str) -> bool:
        """
        Validate if a string is a valid PostgreSQL identifier.

        Args:
            identifier: String to validate

        Returns:
            True if valid identifier, False otherwise
        """
        # PostgreSQL identifiers: alphanumeric, underscore, can start with letter or underscore
        pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
        return bool(re.match(pattern, identifier))

    @staticmethod
    def _classify_connection_error(error: Exception) -> DatabaseConnectionError:
        """Map common asyncpg and network errors to stable API error codes."""
        message = str(error).strip() or error.__class__.__name__
        lowered = message.lower()

        if isinstance(error, asyncpg_exceptions.InvalidPasswordError):
            return DatabaseConnectionError(
                code="INVALID_CREDENTIALS",
                message="Authentication failed. Check the username and password.",
                status_code=401,
            )

        if isinstance(error, asyncpg_exceptions.InvalidCatalogNameError):
            return DatabaseConnectionError(
                code="DATABASE_NOT_FOUND",
                message="The specified database does not exist or is not accessible.",
                status_code=404,
            )

        if isinstance(error, asyncpg_exceptions.InsufficientPrivilegeError):
            return DatabaseConnectionError(
                code="INSUFFICIENT_PRIVILEGES",
                message="The database user does not have permission to access this database.",
                status_code=403,
            )

        if isinstance(error, asyncpg_exceptions.TooManyConnectionsError):
            return DatabaseConnectionError(
                code="TOO_MANY_CONNECTIONS",
                message="The database server has reached its connection limit. Try again shortly.",
                status_code=503,
            )

        if isinstance(error, (TimeoutError, socket.timeout)):
            return DatabaseConnectionError(
                code="CONNECTION_TIMEOUT",
                message="Timed out while trying to connect to the database server.",
                status_code=504,
            )

        if isinstance(error, socket.gaierror):
            return DatabaseConnectionError(
                code="HOST_RESOLUTION_FAILED",
                message="The database host could not be resolved. Check the hostname.",
                status_code=503,
            )

        if "no pg_hba.conf entry" in lowered and "no encryption" in lowered:
            return DatabaseConnectionError(
                code="SSL_REQUIRED",
                message="This database server requires SSL. Retry the connection with ssl=true.",
                status_code=400,
            )

        if "password authentication failed" in lowered:
            return DatabaseConnectionError(
                code="INVALID_CREDENTIALS",
                message="Authentication failed. Check the username and password.",
                status_code=401,
            )

        if isinstance(error, (ConnectionRefusedError, OSError)):
            if "ssl" in lowered:
                return DatabaseConnectionError(
                    code="SSL_ERROR",
                    message="The database rejected the SSL configuration for this connection.",
                    status_code=502,
                )
            if "timeout" in lowered or "timed out" in lowered:
                return DatabaseConnectionError(
                    code="CONNECTION_TIMEOUT",
                    message="Timed out while trying to connect to the database server.",
                    status_code=504,
                )
            if "refused" in lowered or "connect call failed" in lowered:
                return DatabaseConnectionError(
                    code="CONNECTION_REFUSED",
                    message="The database server refused the connection. Check the host and port.",
                    status_code=503,
                )
            if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
                return DatabaseConnectionError(
                    code="HOST_RESOLUTION_FAILED",
                    message="The database host could not be resolved. Check the hostname.",
                    status_code=503,
                )

        return DatabaseConnectionError(
            code="CONNECTION_FAILED",
            message=f"Failed to connect to the database: {message}",
            status_code=500,
        )

    @staticmethod
    def _build_ssl_config(ssl_enabled: Optional[bool]):
        """
        Convert the API's boolean SSL flag into asyncpg SSL settings.

        `ssl=True` means "require an encrypted connection".
        `ssl=False` disables SSL.
        `ssl=None` lets the driver choose its default behavior.
        """
        if ssl_enabled is None:
            return None

        if ssl_enabled is False:
            return False

        ssl_context = ssl_lib.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl_lib.CERT_NONE
        return ssl_context
