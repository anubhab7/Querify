"""
Chat Session Management.
Handles conversation history, context, and pronoun resolution.
"""

import re
import uuid
from typing import Optional, List
from datetime import datetime
from models.schema import ChatMessage, MessageRole
import logging

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages chat sessions with history and context."""

    def __init__(self, session_id: Optional[str] = None, max_history: int = 8):
        """
        Initialize a chat session.

        Args:
            session_id: Optional session ID (generates new one if not provided)
            max_history: Maximum number of messages to keep in history
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.messages: List[ChatMessage] = []
        self.max_history = max_history
        self.last_referenced_table: Optional[str] = None
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

    def add_message(self, role: MessageRole, content: str) -> None:
        """
        Add a message to the session history.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
        """
        self.messages.append(ChatMessage(role=role, content=content))
        self.last_activity = datetime.now()

        # Trim history if exceeds max
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history :]

    def get_history(self, include_system: bool = False) -> List[ChatMessage]:
        """
        Get message history.

        Args:
            include_system: Whether to include system messages

        Returns:
            List of messages
        """
        if include_system:
            return self.messages
        return [m for m in self.messages if m.role != MessageRole.SYSTEM]

    def update_last_referenced_table(self, sql_query: str) -> None:
        """
        Extract and update the last referenced table from a SQL query.

        Uses regex to identify table names from FROM and JOIN clauses.

        Args:
            sql_query: SQL query to analyze
        """
        table_name = self._extract_table_from_query(sql_query)
        if table_name:
            self.last_referenced_table = table_name
            logger.debug(f"Updated last referenced table: {table_name}")

    def resolve_pronouns(self, user_input: str) -> str:
        """
        Replace pronouns like "it" or "that table" with the last referenced table.

        Args:
            user_input: User input text

        Returns:
            Resolved text with pronouns replaced
        """
        if not self.last_referenced_table:
            return user_input

        resolved = user_input

        # Pattern 1: "it" or "It" as standalone word (not part of other words)
        resolved = re.sub(
            r"\bit\b",
            self.last_referenced_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )

        # Pattern 2: "that table" or "That Table"
        resolved = re.sub(
            r"\bthat\s+table\b",
            self.last_referenced_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )

        # Pattern 3: "the table" when preceded by context
        if "the table" in resolved.lower() and len(resolved) < 200:
            resolved = re.sub(
                r"\bthe\s+table\b",
                self.last_referenced_table,
                resolved,
                flags=re.IGNORECASE,
                count=1,
            )

        # Pattern 4: "this table"
        resolved = re.sub(
            r"\bthis\s+table\b",
            self.last_referenced_table,
            resolved,
            flags=re.IGNORECASE,
            count=1,
        )

        if resolved != user_input:
            logger.debug(
                f"Resolved pronouns: '{user_input}' -> '{resolved}'"
            )

        return resolved

    def clear(self) -> None:
        """Clear chat history."""
        self.messages = []
        self.last_referenced_table = None
        logger.debug(f"Cleared session {self.session_id}")

    def to_dict(self) -> dict:
        """
        Convert session to dictionary.

        Returns:
            Session data as dict
        """
        return {
            "session_id": self.session_id,
            "messages": [
                {"role": m.role.value, "content": m.content}
                for m in self.messages
            ],
            "last_referenced_table": self.last_referenced_table,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }

    @staticmethod
    def _extract_table_from_query(sql_query: str) -> Optional[str]:
        """
        Extract the primary table name from a SQL query.

        Looks for FROM and JOIN clauses.

        Args:
            sql_query: SQL query string

        Returns:
            Table name or None
        """
        if not sql_query:
            return None

        try:
            # Pattern for FROM clause: FROM schema.table
            from_match = re.search(
                r"\bFROM\s+(?:(\w+)\.)?(\w+)",
                sql_query,
                re.IGNORECASE
            )

            if from_match:
                schema = from_match.group(1)
                table = from_match.group(2)
                return f"{schema}.{table}" if schema else table

            # Pattern for JOIN clause if no FROM found
            join_match = re.search(
                r"\bJOIN\s+(?:(\w+)\.)?(\w+)",
                sql_query,
                re.IGNORECASE
            )

            if join_match:
                schema = join_match.group(1)
                table = join_match.group(2)
                return f"{schema}.{table}" if schema else table

            return None

        except Exception as e:
            logger.error(f"Error extracting table from query: {e}")
            return None


class ChatSessionManager:
    """Manages multiple chat sessions."""

    def __init__(self, session_timeout_minutes: int = 60):
        """
        Initialize session manager.

        Args:
            session_timeout_minutes: Minutes before a session expires
        """
        self.sessions: dict = {}
        self.session_timeout_minutes = session_timeout_minutes

    def create_session(self, session_id: Optional[str] = None) -> ChatSession:
        """
        Create a new chat session.

        Args:
            session_id: Optional custom session ID

        Returns:
            New ChatSession instance
        """
        session = ChatSession(session_id=session_id)
        self.sessions[session.session_id] = session
        logger.info(f"Created new session: {session.session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Retrieve a session by ID.

        Args:
            session_id: Session ID

        Returns:
            ChatSession or None if not found
        """
        session = self.sessions.get(session_id)

        if session:
            # Check if session has expired
            elapsed_minutes = (
                datetime.now() - session.last_activity
            ).total_seconds() / 60

            if elapsed_minutes > self.session_timeout_minutes:
                logger.warning(f"Session {session_id} expired")
                del self.sessions[session_id]
                return None

        return session

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """
        Remove all expired sessions.

        Returns:
            Number of sessions removed
        """
        expired_sessions = []

        for session_id, session in self.sessions.items():
            elapsed_minutes = (
                datetime.now() - session.last_activity
            ).total_seconds() / 60

            if elapsed_minutes > self.session_timeout_minutes:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self.sessions[session_id]

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

        return len(expired_sessions)

    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.sessions)
