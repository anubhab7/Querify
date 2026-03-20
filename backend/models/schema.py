"""
Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field, SecretStr
from typing import List, Optional, Dict, Any
from enum import Enum


class MessageRole(str, Enum):
    """Message roles in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Represents a single message in conversation history."""
    role: MessageRole
    content: str


class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    user_input: str = Field(..., min_length=1, description="Natural language query")
    session_id: Optional[str] = Field(None, description="Chat session ID for context")
    preferred_model: Optional[str] = Field(
        "gemini",
        description="Preferred LLM model: 'gemini' or 'perplexity'"
    )


class QueryResponse(BaseModel):
    """Response model for /query endpoint."""
    session_id: str = Field(..., description="Chat session ID")
    sql_query: str = Field(..., description="Generated SQL query")
    explanation: str = Field(..., description="Explanation of what the query does")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Query results")
    error: Optional[str] = Field(None, description="Error message if query generation failed")


class KPISuggestion(BaseModel):
    """Single KPI suggestion."""
    number: int = Field(..., description="KPI number")
    name: str = Field(..., description="KPI name")
    description: str = Field(..., description="KPI description")


class KPIRequest(BaseModel):
    """Request model for /kpis endpoint."""
    database_schema: Optional[str] = Field(
        None,
        description="Database schema (if not provided, will be fetched automatically)"
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
    ssl: Optional[bool] = Field(None, description="SSL mode used during the connection test")


class SchemaRequest(BaseModel):
    """Request model for /schema endpoint."""
    pass


class SchemaResponse(BaseModel):
    """Response model for /schema endpoint."""
    # We rename 'schema' to 'db_schema' to avoid shadowing Pydantic's internal 'schema' method
    db_schema: str = Field(..., alias="schema", description="Compact database schema")

    class Config:
        # This allows the model to be initialized using the original name 'schema'
        populate_by_name = True


class ChatSessionRequest(BaseModel):
    """Request model for chat session operations."""
    session_id: Optional[str] = Field(None, description="Session ID to retrieve")


class ChatSessionResponse(BaseModel):
    """Response model for chat session data."""
    session_id: str = Field(..., description="Session ID")
    messages: List[ChatMessage] = Field(..., description="Message history")
    last_referenced_table: Optional[str] = Field(
        None,
        description="Last table referenced in SQL queries"
    )


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
