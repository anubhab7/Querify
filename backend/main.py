"""
Querify FastAPI Web Service
Converts natural language to PostgreSQL queries using LLMs (Gemini & Perplexity)
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings

from services.database_service import DatabaseService, DatabaseConnectionError
from services.llm_service import LLMService
from services.chat_session import ChatSessionManager, MessageRole
from models.schema import (
    QueryRequest,
    QueryResponse,
    KPIRequest,
    KPIResponse,
    KPISuggestion,
    TestConnectionRequest,
    TestConnectionResponse,
    DatabaseConnectRequest,
    DatabaseConnectResponse,
    SchemaRequest,
    SchemaResponse,
    ChatSessionRequest,
    ChatSessionResponse,
    ErrorResponse,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Settings
class Settings(BaseSettings):
    """Application settings from environment variables."""

    database_url: str = "postgresql://user:password@localhost:5432/querify_db"
    gemini_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False
    cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
    ]
    max_history_messages: int = 8

    class Config:
        env_file = ".env"
        case_sensitive = False


# Initialize settings
settings = Settings()

# Global services
db_service: Optional[DatabaseService] = None
llm_service: Optional[LLMService] = None
session_manager: Optional[ChatSessionManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.
    Handles startup and shutdown events.
    """
    global db_service, llm_service, session_manager

    # Startup
    logger.info("Starting Querify API...")

    try:
        # Initialize services
        db_service = DatabaseService(settings.database_url)
        await db_service.connect()
        logger.info("Database connection pool initialized")

        llm_service = LLMService(
            gemini_api_key=settings.gemini_api_key,
            perplexity_api_key=settings.perplexity_api_key,
        )
        logger.info("LLM service initialized")

        session_manager = ChatSessionManager()
        logger.info("Session manager initialized")

        logger.info("Querify API started successfully")

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Querify API...")

    try:
        if db_service:
            await db_service.disconnect()
            logger.info("Database connection pool closed")

        if session_manager:
            removed = session_manager.cleanup_expired_sessions()
            logger.info(f"Cleaned up {removed} expired sessions")

        logger.info("Querify API shutdown complete")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI app
app = FastAPI(
    title="Querify API",
    description="Convert Natural Language to PostgreSQL queries using LLMs",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseConnectionError)
async def database_connection_exception_handler(request, exc: DatabaseConnectionError):
    """Return structured connection errors for database auth/connectivity issues."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "detail": exc.message,
        },
    )


# ============================================================================
# Health & Connection Check Endpoints
# ============================================================================


@app.get("/health", response_model=dict, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "querify",
        "version": "1.0.0",
    }


@app.post(
    "/test-connection",
    response_model=TestConnectionResponse,
    tags=["Database"],
)
async def test_connection(request: TestConnectionRequest = TestConnectionRequest()):
    """
    Test database connection.

    Returns:
        Connection status and result
    """
    if not db_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service not initialized",
        )

    try:
        success = await db_service.test_connection()

        if success:
            return TestConnectionResponse(
                success=True,
                message="Database connection successful",
                database="querify_db",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed",
            )

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test error: {str(e)}",
        )


@app.post(
    "/database/connect",
    response_model=DatabaseConnectResponse,
    tags=["Database"],
)
async def connect_to_user_database(request: DatabaseConnectRequest):
    """
    Test a user-supplied PostgreSQL connection without replacing the app's main database.

    Returns:
        Connection status and the database target that was tested
    """
    try:
        await DatabaseService.test_credentials(
            host=request.host.strip(),
            port=request.port,
            database=request.database.strip(),
            username=request.username.strip(),
            password=request.password.get_secret_value(),
            ssl=request.ssl,
        )

        return DatabaseConnectResponse(
            success=True,
            message="Database connection successful",
            database=request.database.strip(),
            host=request.host.strip(),
            port=request.port,
            ssl=request.ssl,
        )

    except DatabaseConnectionError:
        raise
    except Exception as e:
        logger.error(f"Unexpected database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "CONNECTION_FAILED",
                "detail": f"Unexpected database connection error: {str(e)}",
            },
        )


# ============================================================================
# Schema Endpoints
# ============================================================================


@app.get("/schema", response_model=SchemaResponse, tags=["Database"])
async def get_schema(request: SchemaRequest = SchemaRequest()):
    """
    Get compact database schema.

    Returns:
        Formatted schema: schema.table: col1, col2, col3
    """
    if not db_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database service not initialized",
        )

    try:
        schema = await db_service.get_compact_database_schema()

        return SchemaResponse(schema=schema)

    except Exception as e:
        logger.error(f"Error retrieving schema: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving schema: {str(e)}",
        )


# ============================================================================
# Query Generation Endpoints
# ============================================================================


@app.post("/query", response_model=QueryResponse, tags=["Query Generation"])
async def generate_query(request: QueryRequest):
    """
    Generate SQL query from natural language input.

    Args:
        request: QueryRequest with user_input, optional session_id, preferred_model

    Returns:
        Generated SQL query, explanation, and results (if applicable)
    """
    if not db_service or not llm_service or not session_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Services not initialized",
        )

    try:
        # Validate input
        if not request.user_input or not request.user_input.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_input cannot be empty",
            )

        # Get or create session
        if request.session_id:
            session = session_manager.get_session(request.session_id)
            if not session:
                logger.warning(
                    f"Session {request.session_id} not found, creating new"
                )
                session = session_manager.create_session(request.session_id)
        else:
            session = session_manager.create_session()

        # Resolve pronouns in user input
        resolved_input = session.resolve_pronouns(request.user_input)

        # Get database schema
        schema = await db_service.get_compact_database_schema()

        # Get chat history
        history = session.get_history(include_system=False)

        # Generate SQL query
        sql_query, explanation, model_used = await llm_service.generate_sql_query(
            user_input=resolved_input,
            database_schema=schema,
            chat_history=history,
            preferred_model=request.preferred_model or "gemini",
        )

        if not sql_query:
            # Add to history and return error response
            session.add_message(MessageRole.USER, resolved_input)
            session.add_message(
                MessageRole.ASSISTANT,
                f"Could not generate SQL query. Please try rephrasing your question.",
            )

            return QueryResponse(
                session_id=session.session_id,
                sql_query="",
                explanation=explanation or "Failed to generate query",
                results=[],
                error="Could not generate SQL query",
            )

        # Validate query safety
        is_safe, error_msg = await db_service.is_safe_select_query(sql_query)

        if not is_safe:
            session.add_message(MessageRole.USER, resolved_input)
            session.add_message(
                MessageRole.ASSISTANT,
                f"Generated query is not safe to execute: {error_msg}",
            )

            return QueryResponse(
                session_id=session.session_id,
                sql_query=sql_query,
                explanation=explanation or "",
                results=[],
                error=f"Query validation failed: {error_msg}",
            )

        # Execute query
        try:
            results = await db_service.execute_select_query(sql_query)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            results = []

            return QueryResponse(
                session_id=session.session_id,
                sql_query=sql_query,
                explanation=explanation or "",
                results=[],
                error=f"Query execution error: {str(e)}",
            )

        # Update session with query context
        session.add_message(MessageRole.USER, resolved_input)
        session.add_message(MessageRole.ASSISTANT, explanation or "")
        session.update_last_referenced_table(sql_query)

        return QueryResponse(
            session_id=session.session_id,
            sql_query=sql_query,
            explanation=explanation or "",
            results=results,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating query: {str(e)}",
        )


# ============================================================================
# KPI Suggestion Endpoints
# ============================================================================


@app.post("/kpis", response_model=KPIResponse, tags=["KPI Suggestions"])
async def get_kpi_suggestions(request: KPIRequest):
    """
    Generate business KPI suggestions based on database schema.

    Args:
        request: KPIRequest with optional database_schema

    Returns:
        List of 4 suggested KPIs with explanations
    """
    if not db_service or not llm_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Services not initialized",
        )

    try:
        # Get schema if not provided
        schema = request.database_schema
        if not schema:
            schema = await db_service.get_compact_database_schema()

        if not schema:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not retrieve database schema",
            )

        # Generate KPI suggestions
        kpis, explanation, model_used = await llm_service.generate_kpi_suggestions(
            database_schema=schema,
            preferred_model="gemini",
        )

        if not kpis:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate KPI suggestions",
            )

        # Convert to KPISuggestion objects
        kpi_suggestions = [
            KPISuggestion(
                number=kpi.get("number", i + 1),
                name=kpi.get("name", ""),
                description=kpi.get("description", ""),
            )
            for i, kpi in enumerate(kpis[:4])  # Limit to 4
        ]

        return KPIResponse(
            kpis=kpi_suggestions,
            explanation=explanation or "KPI suggestions generated successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating KPI suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating KPI suggestions: {str(e)}",
        )


# ============================================================================
# Chat Session Endpoints
# ============================================================================


@app.get("/session/{session_id}", response_model=ChatSessionResponse, tags=["Sessions"])
async def get_session(session_id: str):
    """
    Retrieve chat session data.

    Args:
        session_id: Session ID

    Returns:
        Session data with message history
    """
    if not session_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session manager not initialized",
        )

    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return ChatSessionResponse(
        session_id=session.session_id,
        messages=[
            {"role": m.role.value, "content": m.content}
            for m in session.get_history()
        ],
        last_referenced_table=session.last_referenced_table,
    )


@app.delete("/session/{session_id}", tags=["Sessions"])
async def delete_session(session_id: str):
    """
    Delete a chat session.

    Args:
        session_id: Session ID

    Returns:
        Success message
    """
    if not session_manager:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session manager not initialized",
        )

    if session_manager.delete_session(session_id):
        return {"message": f"Session {session_id} deleted"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail or "Internal server error",
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info",
    )
