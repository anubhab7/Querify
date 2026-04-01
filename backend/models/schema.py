"""
Pydantic models for API requests and responses.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


class MessageRole(str, Enum):
    """Message roles in conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Represents a single LLM history message."""

    role: MessageRole
    content: str


class UserRegisterRequest(BaseModel):
    """Request model for user registration."""

    email: EmailStr
    password: SecretStr = Field(..., min_length=8)


class UserLoginRequest(BaseModel):
    """Request model for user login."""

    email: EmailStr
    password: SecretStr


class UserResponse(BaseModel):
    """Serialized user information."""

    id: str
    email: EmailStr
    created_at: datetime


class AuthResponse(BaseModel):
    """JWT authentication response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class QueryRequest(BaseModel):
    """Request model for /query endpoint."""

    user_input: str = Field(..., min_length=1, description="Natural language query")
    session_id: str = Field(..., description="Chat session ID containing target DB credentials")
    preferred_model: Optional[str] = Field(
        "gemini",
        description="Preferred LLM model: 'gemini' or 'perplexity'",
    )


class QueryResponse(BaseModel):
    """Response model for /query endpoint."""

    session_id: str = Field(..., description="Chat session ID")
    sql_query: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of what the query does")
    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Query results"
    )
    error: Optional[str] = Field(
        None, description="Error message if query generation failed"
    )


class KPISuggestion(BaseModel):
    """Single KPI suggestion."""

    number: int = Field(..., description="KPI number")
    name: str = Field(..., description="KPI name")
    description: str = Field(..., description="KPI description")


class KPIRequest(BaseModel):
    """Request model for /kpis endpoint."""

    session_id: str = Field(..., description="Chat session ID")
    database_schema: Optional[str] = Field(
        None,
        description="Database schema (if not provided, will be fetched automatically)",
    )


class KPIResponse(BaseModel):
    """Response model for /kpis endpoint."""

    kpis: List[KPISuggestion] = Field(..., description="List of suggested KPIs")
    explanation: str = Field(..., description="Overall explanation of suggested KPIs")


class TestConnectionRequest(BaseModel):
    """Request model for /test-connection endpoint."""

    pass


class TestConnectionResponse(BaseModel):
    """Response model for /test-connection endpoint."""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Status message")
    database: Optional[str] = Field(None, description="Database being connected to")


class DatabaseConnectRequest(BaseModel):
    """Request model for testing user-supplied PostgreSQL credentials."""

    host: str = Field(..., min_length=1, description="PostgreSQL host")
    port: int = Field(5432, ge=1, le=65535, description="PostgreSQL port")
    database: str = Field(..., min_length=1, description="Database name")
    username: str = Field(..., min_length=1, description="Database username")
    password: SecretStr = Field(..., description="Database password")
    ssl: Optional[bool] = Field(
        None,
        description="Set true to require SSL, false to disable it, or omit to use driver defaults",
    )


class DatabaseConnectResponse(BaseModel):
    """Response model for user-supplied PostgreSQL connection tests."""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Connection status message")
    database: str = Field(..., description="Database that was tested")
    host: str = Field(..., description="Database host that was tested")
    port: int = Field(..., description="Database port that was tested")
    ssl: Optional[bool] = Field(
        None, description="SSL mode used during the connection test"
    )


class SchemaResponse(BaseModel):
    """Response model for /schema endpoint."""

    db_schema: str = Field(..., alias="schema", description="Compact database schema")

    model_config = ConfigDict(populate_by_name=True)


class ChatCreateRequest(BaseModel):
    """Request model for creating a new chat."""

    title: Optional[str] = Field(None, description="Optional chat title")
    host: str = Field(..., min_length=1, description="Target PostgreSQL host")
    port: int = Field(5432, ge=1, le=65535, description="Target PostgreSQL port")
    database: str = Field(..., min_length=1, description="Target database name")
    username: str = Field(..., min_length=1, description="Target database username")
    password: SecretStr = Field(..., description="Target database password")
    ssl: Optional[bool] = Field(
        None,
        description="Whether to require SSL for the target database connection",
    )


class ChatSummary(BaseModel):
    """Summary view for a chat."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_referenced_table: Optional[str] = None


class ChatSessionResponse(BaseModel):
    """Response model for chat creation."""

    session_id: str = Field(..., description="Session ID")
    title: str = Field(..., description="Chat title")
    created_at: datetime
    last_referenced_table: Optional[str] = Field(
        None, description="Last table referenced in SQL queries"
    )


class PersistedMessageResponse(BaseModel):
    """Persisted query turn stored in the messages table."""

    id: str
    chat_id: str
    user_input: str
    sql_query: str
    explanation: str
    results: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """Response model for full chat history."""

    chat_id: str
    title: str
    messages: List[PersistedMessageResponse]


class ChatStatusResponse(BaseModel):
    """Reachability status for a chat's target database."""

    chat_id: str
    reachable: bool
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
