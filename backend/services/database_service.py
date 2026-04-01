"""
Database service for PostgreSQL operations.
Handles persistent app storage, target-database connections, schema retrieval,
query safety validation, and data sampling.
"""

import logging
import re
import socket
import ssl as ssl_lib
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import asyncpg
from asyncpg import exceptions as asyncpg_exceptions
from sqlparse import parse

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Structured database connection error."""

    def __init__(self, code: str, message: str, status_code: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DatabaseService:
    """Service for database operations with permanent and temporary pools."""

    def __init__(
        self,
        connection_string: str,
        *,
        ssl: Optional[bool] = None,
        permanent_pool: bool = False,
    ):
        self.connection_string = connection_string
        self.ssl = ssl
        self.permanent_pool = permanent_pool
        self.pool: Optional[asyncpg.Pool] = None

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
        quoted_username = quote(username.strip(), safe="")
        quoted_password = quote(password, safe="")
        quoted_database = quote(database.strip(), safe="")
        return (
            f"postgresql://{quoted_username}:{quoted_password}"
            f"@{host.strip()}:{port}/{quoted_database}"
        )

    @classmethod
    def from_credentials(
        cls,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ssl: Optional[bool] = None,
        permanent_pool: bool = False,
    ) -> "DatabaseService":
        """Create a DatabaseService from discrete PostgreSQL credentials."""
        return cls(
            cls.build_connection_string(
                host=host,
                port=port,
                database=database,
                username=username,
                password=password,
            ),
            ssl=ssl,
            permanent_pool=permanent_pool,
        )

    async def __aenter__(self) -> "DatabaseService":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Create a connection pool to PostgreSQL."""
        if self.pool is not None:
            return

        try:
            pool_kwargs = {
                "dsn": self.connection_string,
                "timeout": 10,
                "command_timeout": 20,
                "ssl": self._build_ssl_config(self.ssl),
            }
            if self.permanent_pool:
                pool_kwargs.update({"min_size": 1, "max_size": 5})
            else:
                pool_kwargs.update({"min_size": 1, "max_size": 1})

            self.pool = await asyncpg.create_pool(**pool_kwargs)
            logger.info(
                "Database connection pool created successfully (permanent=%s)",
                self.permanent_pool,
            )
        except Exception as e:
            classified_error = self._classify_connection_error(e)
            logger.error(
                "Failed to create database connection pool [%s]: %s",
                classified_error.code,
                classified_error.message,
            )
            raise classified_error from e

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")

    async def ensure_connected(self) -> None:
        """Ensure the pool is connected before using it."""
        if not self.pool:
            await self.connect()

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows from the current database."""
        await self.ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row from the current database."""
        await self.ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single scalar value from the current database."""
        await self.ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            return await connection.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a statement against the current database."""
        await self.ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def initialize_app_schema(self) -> None:
        """Create or migrate the tables used for authentication and chat persistence."""
        await self.ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            await connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS email TEXT;
                """
            )
            await connection.execute(
                """
                UPDATE users
                SET email = username
                WHERE email IS NULL;
                """
            )
            await connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
                ON users(email);
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    target_db_host TEXT,
                    target_db_port INTEGER,
                    target_db_name TEXT,
                    target_db_user TEXT,
                    target_db_password TEXT,
                    target_db_ssl BOOLEAN,
                    db_host TEXT NOT NULL,
                    db_port INTEGER NOT NULL,
                    db_name TEXT NOT NULL,
                    db_username TEXT NOT NULL,
                    db_password TEXT NOT NULL,
                    db_ssl BOOLEAN,
                    last_referenced_table TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_host TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_port INTEGER;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_name TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_username TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_password TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS db_ssl BOOLEAN;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS last_referenced_table TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
                """
            )
            await connection.execute(
                """
                UPDATE chats
                SET
                    db_host = COALESCE(db_host, target_db_host),
                    db_port = COALESCE(db_port, target_db_port, 5432),
                    db_name = COALESCE(db_name, target_db_name),
                    db_username = COALESCE(db_username, target_db_user),
                    db_password = COALESCE(db_password, target_db_password),
                    db_ssl = COALESCE(db_ssl, target_db_ssl, true),
                    updated_at = COALESCE(updated_at, last_activity, created_at, NOW())
                WHERE
                    db_host IS NULL
                    OR db_port IS NULL
                    OR db_name IS NULL
                    OR db_username IS NULL
                    OR db_password IS NULL
                    OR db_ssl IS NULL
                    OR updated_at IS NULL;
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY,
                    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT,
                    content TEXT,
                    user_input TEXT NOT NULL,
                    sql_query TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    timestamp TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            await connection.execute(
                """
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_input TEXT;
                """
            )
            await connection.execute(
                """
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
                """
            )
            await connection.execute(
                """
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS results JSONB;
                """
            )
            await connection.execute(
                """
                UPDATE messages
                SET
                    user_input = COALESCE(user_input, content),
                    created_at = COALESCE(created_at, timestamp, NOW())
                WHERE user_input IS NULL OR created_at IS NULL;
                """
            )
            await connection.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'messages'
                          AND column_name = 'results'
                          AND data_type <> 'jsonb'
                    ) THEN
                        ALTER TABLE messages
                        ALTER COLUMN results TYPE JSONB
                        USING CASE
                            WHEN results IS NULL OR BTRIM(results) = '' THEN '[]'::jsonb
                            ELSE results::jsonb
                        END;
                    END IF;
                END
                $$;
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chats_user_id_created_at
                    ON chats(user_id, created_at DESC);
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chats_user_id_updated_at
                    ON chats(user_id, updated_at DESC);
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created_at
                    ON messages(chat_id, created_at ASC);
                """
            )

    async def test_connection(self) -> bool:
        """Test the current database connection."""
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error("Database connection test failed: %s", e)
            return False

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
        async with cls.from_credentials(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            ssl=ssl,
            permanent_pool=False,
        ) as service:
            await service.fetchval("SELECT 1")

    async def get_compact_database_schema(self) -> str:
        """
        Retrieve the database schema in compact format.

        Returns schema as: schema.table: col1, col2, col3
        """
        try:
            rows = await self.fetch(
                """
                SELECT
                    t.table_schema,
                    t.table_name,
                    STRING_AGG(c.column_name, ', ' ORDER BY c.ordinal_position) AS columns
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c
                    ON t.table_schema = c.table_schema
                    AND t.table_name = c.table_name
                WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
                GROUP BY t.table_schema, t.table_name
                ORDER BY t.table_schema, t.table_name;
                """
            )

            schema_lines = []
            for row in rows:
                schema_lines.append(
                    f"{row['table_schema']}.{row['table_name']}: {row['columns'] or ''}"
                )
            return "\n".join(schema_lines)
        except Exception as e:
            logger.error("Error retrieving database schema: %s", e)
            raise

    async def get_column_value_samples(
        self, schema: str, table: str, column: str, limit: int = 5
    ) -> List[str]:
        """Fetch distinct values from a column to help the LLM with filtering."""
        try:
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
            rows = await self.fetch(query)
            return [str(row[column]) for row in rows]
        except Exception as e:
            logger.error(
                "Error retrieving column samples from %s.%s.%s: %s",
                schema,
                table,
                column,
                e,
            )
            return []

    async def is_safe_select_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a query is safe to execute (only SELECT and WITH statements).
        """
        if not query or not query.strip():
            return False, "Query is empty"

        normalized_query = query.strip()
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

        for pattern in dangerous_patterns:
            if re.search(pattern, normalized_query, re.IGNORECASE):
                return False, f"Query contains forbidden keyword: {pattern}"

        try:
            parsed = parse(normalized_query)
            if not parsed:
                return False, "Could not parse query"

            for statement in parsed:
                first_token = None
                for token in statement.tokens:
                    if not token.is_whitespace:
                        first_token = token
                        break

                if first_token is None:
                    return False, "Query has no valid tokens"

                token_value = str(first_token).upper().strip()
                if token_value not in ("SELECT", "WITH"):
                    return (
                        False,
                        f"Only SELECT and WITH queries are allowed, got: {token_value}",
                    )

            return True, None
        except Exception as e:
            logger.error("Error parsing query: %s", e)
            return False, f"Could not parse query: {str(e)}"

    async def execute_select_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a validated SELECT query and return results."""
        is_safe, error_msg = await self.is_safe_select_query(query)
        if not is_safe:
            raise ValueError(f"Unsafe query: {error_msg}")

        try:
            rows = await self.fetch(query)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Error executing query: %s", e)
            raise

    @staticmethod
    def _is_valid_identifier(identifier: str) -> bool:
        """Validate if a string is a valid PostgreSQL identifier."""
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier))

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
            if (
                "name or service not known" in lowered
                or "nodename nor servname provided" in lowered
            ):
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
        """
        if ssl_enabled is None:
            return None

        if ssl_enabled is False:
            return False

        ssl_context = ssl_lib.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl_lib.CERT_NONE
        return ssl_context
