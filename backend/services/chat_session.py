"""
Persistent chat session management backed by the app database.
Handles chat storage, message history, and pronoun resolution.
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from models.schema import ChatMessage, MessageRole
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class ChatSessionManager:
    """Manages persistent chat sessions stored in PostgreSQL."""

    def __init__(self, app_db: DatabaseService, max_history: int = 8):
        self.app_db = app_db
        self.max_history = max_history

    async def create_chat(
        self,
        *,
        user_id: str,
        title: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        ssl: Optional[bool],
    ) -> Dict:
        """Create a new persistent chat with target DB credentials."""
        chat_id = str(uuid.uuid4())
        row = await self.app_db.fetchrow(
            """
            INSERT INTO chats (
                id, user_id, title, db_host, db_port, db_name, db_username, db_password, db_ssl
            )
            VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id, title, created_at, updated_at, last_referenced_table;
            """,
            chat_id,
            user_id,
            title,
            host.strip(),
            port,
            database.strip(),
            username.strip(),
            password,
            ssl,
        )
        assert row is not None
        logger.info("Created chat %s for user %s", chat_id, user_id)
        return dict(row)

    async def get_chat(self, chat_id: str, user_id: str) -> Optional[Dict]:
        """Fetch a chat and its target DB credentials for a user."""
        row = await self.app_db.fetchrow(
            """
            SELECT
                id,
                user_id,
                title,
                db_host,
                db_port,
                db_name,
                db_username,
                db_password,
                db_ssl,
                last_referenced_table,
                created_at,
                updated_at
            FROM chats
            WHERE id = $1::uuid AND user_id = $2::uuid;
            """,
            chat_id,
            user_id,
        )
        return dict(row) if row else None

    async def list_chats(self, user_id: str) -> List[Dict]:
        """List chat summaries for a user."""
        rows = await self.app_db.fetch(
            """
            SELECT
                id,
                title,
                created_at,
                COALESCE(updated_at, last_activity, created_at) AS updated_at,
                last_referenced_table
            FROM chats
            WHERE user_id = $1::uuid
            ORDER BY updated_at DESC, created_at DESC;
            """,
            user_id,
        )
        return [dict(row) for row in rows]

    async def get_chat_history(self, chat_id: str, user_id: str) -> List[Dict]:
        """Fetch persisted history for a chat."""
        rows = await self.app_db.fetch(
            """
            SELECT
                m.id,
                m.chat_id,
                m.user_input,
                m.sql_query,
                m.explanation,
                m.results,
                COALESCE(m.created_at, m.timestamp) AS created_at
            FROM messages m
            INNER JOIN chats c ON c.id = m.chat_id
            WHERE m.chat_id = $1::uuid AND c.user_id = $2::uuid
            ORDER BY COALESCE(m.created_at, m.timestamp) ASC;
            """,
            chat_id,
            user_id,
        )
        history: List[Dict[str, Any]] = []
        for row in rows:
            message = dict(row)
            message["results"] = self._normalize_results_payload(message.get("results"))

            history.append(message)

        return history

    async def get_recent_messages_for_llm(
        self, chat_id: str, user_id: str
    ) -> List[ChatMessage]:
        """Transform recent persisted query turns into chat messages for the LLM."""
        rows = await self.app_db.fetch(
            """
            SELECT
                m.user_input,
                m.explanation,
                COALESCE(m.created_at, m.timestamp) AS created_at
            FROM messages m
            INNER JOIN chats c ON c.id = m.chat_id
            WHERE m.chat_id = $1::uuid AND c.user_id = $2::uuid
            ORDER BY COALESCE(m.created_at, m.timestamp) DESC
            LIMIT $3;
            """,
            chat_id,
            user_id,
            self.max_history,
        )

        messages: List[ChatMessage] = []
        for row in reversed(rows):
            messages.append(ChatMessage(role=MessageRole.USER, content=row["user_input"]))
            messages.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=row["explanation"])
            )
        return messages

    async def append_query_message(
        self,
        *,
        chat_id: str,
        user_input: str,
        sql_query: str,
        explanation: str,
        results: List[Dict[str, Any]],
    ) -> Dict:
        """Persist a query interaction for a chat."""
        message_id = str(uuid.uuid4())
        normalized_results = self._normalize_results_payload(results)
        serialized_results = json.dumps(normalized_results, default=str)
        row = await self.app_db.fetchrow(
            """
            INSERT INTO messages (
                id, chat_id, role, content, user_input, sql_query, explanation, results, timestamp, created_at
            )
            VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, NOW(), NOW())
            RETURNING id, chat_id, user_input, sql_query, explanation, results, created_at;
            """,
            message_id,
            chat_id,
            MessageRole.USER.value,
            user_input,
            user_input,
            sql_query,
            explanation,
            serialized_results,
        )
        await self.touch_chat(chat_id)
        assert row is not None
        message = dict(row)
        message["results"] = self._normalize_results_payload(message.get("results"))
        return message

    async def touch_chat(self, chat_id: str) -> None:
        """Refresh the chat update timestamp."""
        await self.app_db.execute(
            """
            UPDATE chats
            SET updated_at = NOW()
            WHERE id = $1::uuid;
            """,
            chat_id,
        )

    async def update_title(self, chat_id: str, title: str) -> None:
        """Update the persisted title for a chat."""
        await self.app_db.execute(
            """
            UPDATE chats
            SET title = $2, updated_at = NOW()
            WHERE id = $1::uuid;
            """,
            chat_id,
            title,
        )

    async def update_last_referenced_table(self, chat_id: str, sql_query: str) -> None:
        """Persist the last table referenced by the generated SQL query."""
        table_name = self._extract_table_from_query(sql_query)
        await self.app_db.execute(
            """
            UPDATE chats
            SET last_referenced_table = $2, updated_at = NOW()
            WHERE id = $1::uuid;
            """,
            chat_id,
            table_name,
        )

    async def resolve_pronouns(self, chat_id: str, user_input: str) -> str:
        """Resolve lightweight table pronouns using the stored chat context."""
        last_table = await self.app_db.fetchval(
            """
            SELECT last_referenced_table
            FROM chats
            WHERE id = $1::uuid;
            """,
            chat_id,
        )

        if not last_table:
            return user_input

        resolved = re.sub(
            r"\bit\b",
            last_table,
            user_input,
            flags=re.IGNORECASE,
            count=1,
        )
        resolved = re.sub(
            r"\bthat\s+table\b",
            last_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )
        resolved = re.sub(
            r"\bthe\s+table\b",
            last_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )
        resolved = re.sub(
            r"\bthis\s+table\b",
            last_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )
        return resolved

    async def delete_chat(self, chat_id: str, user_id: str) -> bool:
        """Delete a chat that belongs to the given user."""
        result = await self.app_db.execute(
            """
            DELETE FROM chats
            WHERE id = $1::uuid AND user_id = $2::uuid;
            """,
            chat_id,
            user_id,
        )
        return result.endswith("1")

    @staticmethod
    def _extract_table_from_query(sql_query: str) -> Optional[str]:
        """Extract the primary table name from a SQL query."""
        if not sql_query:
            return None

        try:
            from_match = re.search(
                r"\bFROM\s+(?:(\w+)\.)?(\w+)",
                sql_query,
                re.IGNORECASE,
            )
            if from_match:
                schema = from_match.group(1)
                table = from_match.group(2)
                return f"{schema}.{table}" if schema else table

            join_match = re.search(
                r"\bJOIN\s+(?:(\w+)\.)?(\w+)",
                sql_query,
                re.IGNORECASE,
            )
            if join_match:
                schema = join_match.group(1)
                table = join_match.group(2)
                return f"{schema}.{table}" if schema else table

            return None
        except Exception as e:
            logger.error("Error extracting table from query: %s", e)
            return None

    @staticmethod
    def _normalize_results_payload(raw_results: Any) -> List[Dict[str, Any]]:
        """Normalize JSON/JSONB payloads into a safe list-of-dicts shape."""
        if raw_results is None or raw_results == "":
            return []

        if isinstance(raw_results, bytes):
            try:
                raw_results = raw_results.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Failed to decode message results bytes payload")
                return []

        if isinstance(raw_results, str):
            stripped = raw_results.strip()
            if not stripped:
                return []
            try:
                raw_results = json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning("Failed to parse message results JSON")
                return []

        if isinstance(raw_results, dict):
            return [raw_results]

        if not isinstance(raw_results, list):
            return []

        normalized_results: List[Dict[str, Any]] = []
        for row in raw_results:
            if isinstance(row, dict):
                normalized_results.append(row)
            else:
                logger.warning("Skipping non-dictionary message result row: %r", row)

        return normalized_results
