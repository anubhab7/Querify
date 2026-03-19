"""
Database service for PostgreSQL operations.
Handles schema retrieval, query safety validation, and data sampling.
"""

import asyncpg
import re
from typing import List, Dict, Optional, Tuple
from sqlparse import parse, sql
import logging

logger = logging.getLogger(__name__)


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
            self.pool = await asyncpg.create_pool(self.connection_string)
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise

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
