"""
Querify FastAPI Web Service
Refactored to persist chat state and authenticate users with JWTs.
"""

import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.schema import (
    AuthResponse,
    ChatCreateRequest,
    ChatHistoryResponse,
    ChatSessionResponse,
    ChatStatusResponse,
    ChatSummary,
    DatabaseConnectRequest,
    DatabaseConnectResponse,
    KPIRequest,
    KPIResponse,
    KPISuggestion,
    PersistedMessageResponse,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
    TestConnectionRequest,
    TestConnectionResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from services.chat_session import ChatSessionManager
from services.database_service import DatabaseConnectionError, DatabaseService
from services.llm_service import LLMService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Settings(BaseSettings):
    """Application settings from environment variables."""

    database_url: str = "postgresql://user:password@localhost:5432/querify_db"
    app_database_url: Optional[str] = None
    gemini_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    api_host: str = "0.0.0.0"
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("PORT", "api_port"),
    )
    api_debug: bool = False
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
    ]
    max_history_messages: int = 8
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        """Allow CORS origins to be provided as a JSON array or comma-separated string."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def internal_database_url(self) -> str:
        """Prefer APP_DATABASE_URL for app state, with DATABASE_URL as fallback."""
        return self.app_database_url or self.database_url


settings = Settings()

app_db_service: Optional[DatabaseService] = None
llm_service: Optional[LLMService] = None
session_manager: Optional[ChatSessionManager] = None


def api_error_payload(error: str, detail: Optional[str] = None) -> dict:
    """Create a consistent API error response payload."""
    payload = {"error": error}
    if detail:
        payload["detail"] = detail
    return payload


def raise_api_error(
    status_code: int,
    error: str,
    detail: Optional[str] = None,
    headers: Optional[dict] = None,
) -> None:
    """Raise a FastAPI HTTPException with a normalized payload."""
    raise HTTPException(
        status_code=status_code,
        detail=api_error_payload(error, detail),
        headers=headers,
    )


def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against its stored hash."""
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, email: str) -> str:
    """Create a signed JWT for the authenticated user."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Resolve the current user from a Bearer token."""
    if app_db_service is None:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "SERVICE_INITIALIZATION_FAILED",
            "Database service not initialized",
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=api_error_payload("INVALID_TOKEN", "Invalid or expired token"),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    row = await app_db_service.fetchrow(
        """
        SELECT id, email, created_at
        FROM users
        WHERE id = $1::uuid;
        """,
        user_id,
    )
    if row is None:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "USER_NOT_FOUND",
            "User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return dict(row)


async def require_services() -> tuple[DatabaseService, LLMService, ChatSessionManager]:
    """Ensure the global services are available before handling a request."""
    if app_db_service is None or llm_service is None or session_manager is None:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "SERVICE_INITIALIZATION_FAILED",
            "Services not initialized",
        )
    return app_db_service, llm_service, session_manager


async def get_target_database_service(chat: dict) -> DatabaseService:
    """Create a short-lived DatabaseService for the target database linked to a chat."""
    return DatabaseService.from_credentials(
        host=chat["db_host"],
        port=chat["db_port"],
        database=chat["db_name"],
        username=chat["db_username"],
        password=chat["db_password"],
        ssl=chat["db_ssl"],
        permanent_pool=False,
    )


def chat_title_from_request(request: ChatCreateRequest) -> str:
    """Choose a stable chat title when the client does not provide one."""
    if request.title and request.title.strip():
        return request.title.strip()
    return "New chat"


def derive_chat_title_from_query(user_input: str) -> str:
    """Build a short chat title from the first user question."""
    cleaned = re.sub(r"\s+", " ", user_input).strip(" ?!.,")
    words = cleaned.split()

    if not words:
        return "New chat"

    title = " ".join(words[:4]).strip()
    if len(words) > 4:
        title = f"{title}..."

    return title[:80]


def to_user_friendly_query_error(raw_error: str | None) -> str:
    """Translate low-level query failures into concise chat-safe messages."""
    error_text = (raw_error or "").strip()
    lowered = error_text.lower()

    if not error_text:
        return "We couldn't find a result for that query. Please try rephrasing it."
    if "connect" in lowered or "timeout" in lowered or "connection" in lowered:
        return "We couldn't reach the database just now. Please try again in a moment."
    if "syntax" in lowered or "parse" in lowered:
        return "We couldn't run that query successfully. Please try rephrasing it."
    if "validation failed" in lowered or "safe select" in lowered:
        return "We couldn't safely run that request. Please try asking it a different way."
    if "no sql generated" in lowered or "could not generate sql" in lowered:
        return "We couldn't generate a result for that question. Please try rephrasing it."
    return "We couldn't find a result for that query. Please try rephrasing it."


def normalize_kpi_items(raw_kpis) -> list[dict]:
    """Coerce mixed KPI output into the response model's expected dictionary shape."""
    def clean_label(value: str) -> str:
        return value.replace("*", "").replace("`", "").replace("_", "").strip(" :.-").strip()

    if not isinstance(raw_kpis, list):
        return []

    normalized: list[dict] = []
    for index, item in enumerate(raw_kpis, start=1):
        if isinstance(item, KPISuggestion):
            normalized.append(item.model_dump())
            continue

        if not isinstance(item, dict):
            continue

        name = clean_label(
            str(item.get("name") or item.get("title") or item.get("kpi") or "").strip()
        )
        description = clean_label(
            str(
            item.get("description")
            or item.get("details")
            or item.get("reason")
            or item.get("value")
            or ""
            ).strip()
        )

        if name.lower() in {"kpi", "kpi name", "name"} and description:
            name = description

        if not name and description:
            name = description[:80].strip()
        if not description and name:
            description = name
        if not name:
            continue

        try:
            number = int(item.get("number", index))
        except (TypeError, ValueError):
            number = index

        normalized.append(
            {
                "number": number,
                "name": name,
                "description": description,
            }
        )

    return normalized


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    global app_db_service, llm_service, session_manager

    logger.info("Starting Querify API...")

    try:
        app_db_service = DatabaseService(
            settings.internal_database_url,
            permanent_pool=True,
        )
        await app_db_service.connect()
        await app_db_service.initialize_app_schema()
        logger.info("App database connection pool initialized")

        llm_service = LLMService(
            gemini_api_key=settings.gemini_api_key,
            perplexity_api_key=settings.perplexity_api_key,
        )
        logger.info("LLM service initialized")

        session_manager = ChatSessionManager(
            app_db=app_db_service,
            max_history=settings.max_history_messages,
        )
        logger.info("Persistent chat session manager initialized")
        logger.info("Querify API started successfully")
    except Exception as e:
        logger.error("Failed to start application: %s", e)
        raise

    yield

    logger.info("Shutting down Querify API...")
    try:
        if app_db_service:
            await app_db_service.disconnect()
            logger.info("App database connection pool closed")
    except Exception as e:
        logger.error("Error during shutdown: %s", e)


app = FastAPI(
    title="Querify API",
    description="Convert Natural Language to PostgreSQL queries using LLMs",
    version="2.0.0",
    lifespan=lifespan,
)

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
        content={"error": exc.code, "detail": exc.message},
    )


@app.get("/health", response_model=dict, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "querify", "version": "2.0.0"}


@app.post("/auth/register", response_model=AuthResponse, tags=["Authentication"])
async def register(request: UserRegisterRequest):
    """Register a new user and return a JWT."""
    app_db, _, _ = await require_services()
    email = request.email.lower()

    existing_user = await app_db.fetchrow(
        "SELECT id FROM users WHERE email = $1;",
        email,
    )
    if existing_user:
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "USER_ALREADY_EXISTS",
            "A user with this email already exists",
        )

    user_id = str(uuid.uuid4())
    password_hash = hash_password(request.password.get_secret_value())
    row = await app_db.fetchrow(
        """
        INSERT INTO users (id, username, email, password_hash)
        VALUES ($1::uuid, $2, $3, $4)
        RETURNING id, email, created_at;
        """,
        user_id,
        email,
        email,
        password_hash,
    )
    assert row is not None

    token = create_access_token(user_id=str(row["id"]), email=row["email"])
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=str(row["id"]),
            email=row["email"],
            created_at=row["created_at"],
        ),
    )


@app.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
async def login(request: UserLoginRequest):
    """Authenticate a user and return a JWT."""
    app_db, _, _ = await require_services()
    email = request.email.lower()

    row = await app_db.fetchrow(
        """
        SELECT id, email, password_hash, created_at
        FROM users
        WHERE email = $1;
        """,
        email,
    )
    if row is None or not verify_password(
        request.password.get_secret_value(), row["password_hash"]
    ):
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user_id=str(row["id"]), email=row["email"])
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=str(row["id"]),
            email=row["email"],
            created_at=row["created_at"],
        ),
    )


@app.post(
    "/test-connection",
    response_model=TestConnectionResponse,
    tags=["Database"],
)
async def test_connection(request: TestConnectionRequest = TestConnectionRequest()):
    """Test the app database connection."""
    if app_db_service is None:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "SERVICE_INITIALIZATION_FAILED",
            "Database service not initialized",
        )

    success = await app_db_service.test_connection()
    if not success:
        raise_api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CONNECTION_FAILED",
            "Database connection failed",
        )

    return TestConnectionResponse(
        success=True,
        message="Database connection successful",
        database="app_state",
    )


@app.post(
    "/database/connect",
    response_model=DatabaseConnectResponse,
    tags=["Database"],
)
async def connect_to_user_database(request: DatabaseConnectRequest):
    """Test a user-supplied PostgreSQL connection without storing it."""
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
        logger.error("Unexpected database connection error: %s", e)
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "CONNECTION_FAILED",
            f"Unexpected database connection error: {str(e)}",
        )


@app.post("/chats", response_model=ChatSessionResponse, tags=["Chats"])
async def create_chat(
    request: ChatCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new persistent chat with target DB credentials."""
    _, _, chats = await require_services()

    await DatabaseService.test_credentials(
        host=request.host.strip(),
        port=request.port,
        database=request.database.strip(),
        username=request.username.strip(),
        password=request.password.get_secret_value(),
        ssl=request.ssl,
    )

    chat = await chats.create_chat(
        user_id=str(current_user["id"]),
        title=chat_title_from_request(request),
        host=request.host,
        port=request.port,
        database=request.database,
        username=request.username,
        password=request.password.get_secret_value(),
        ssl=request.ssl,
    )
    return ChatSessionResponse(
        session_id=str(chat["id"]),
        title=chat["title"],
        created_at=chat["created_at"],
        last_referenced_table=chat["last_referenced_table"],
    )


@app.get("/chats", response_model=list[ChatSummary], tags=["Chats"])
async def list_chats(current_user: dict = Depends(get_current_user)):
    """List all chats for the authenticated user."""
    _, _, chats = await require_services()
    chat_rows = await chats.list_chats(str(current_user["id"]))
    return [
        ChatSummary(
            id=str(chat["id"]),
            title=chat["title"],
            created_at=chat["created_at"],
            updated_at=chat["updated_at"],
            last_referenced_table=chat["last_referenced_table"],
        )
        for chat in chat_rows
    ]


@app.get(
    "/chats/{chat_id}/history",
    response_model=ChatHistoryResponse,
    tags=["Chats"],
)
async def get_chat_history(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Fetch all persisted messages for a specific chat."""
    _, _, chats = await require_services()
    chat = await chats.get_chat(chat_id, str(current_user["id"]))
    if chat is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {chat_id} not found",
        )

    history = await chats.get_chat_history(chat_id, str(current_user["id"]))
    return ChatHistoryResponse(
        chat_id=str(chat["id"]),
        title=chat["title"],
        messages=[
            PersistedMessageResponse(
                id=str(message["id"]),
                chat_id=str(message["chat_id"]),
                user_input=message["user_input"],
                sql_query=message["sql_query"],
                explanation=message["explanation"],
                results=message.get("results", []),
                created_at=message["created_at"],
            )
            for message in history
        ],
    )


@app.get(
    "/chats/{chat_id}/status",
    response_model=ChatStatusResponse,
    tags=["Chats"],
)
async def get_chat_status(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check if the target database linked to the chat is reachable right now."""
    _, _, chats = await require_services()
    chat = await chats.get_chat(chat_id, str(current_user["id"]))
    if chat is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {chat_id} not found",
        )

    try:
        await DatabaseService.test_credentials(
            host=chat["db_host"],
            port=chat["db_port"],
            database=chat["db_name"],
            username=chat["db_username"],
            password=chat["db_password"],
            ssl=chat["db_ssl"],
        )
        return ChatStatusResponse(
            chat_id=str(chat["id"]),
            reachable=True,
            message="Target database is reachable",
        )
    except DatabaseConnectionError as exc:
        return ChatStatusResponse(
            chat_id=str(chat["id"]),
            reachable=False,
            message=exc.message,
        )


@app.get("/schema", response_model=SchemaResponse, tags=["Database"])
async def get_schema(
    session_id: str = Query(..., description="Chat session ID"),
    current_user: dict = Depends(get_current_user),
):
    """Get the compact schema for the target database linked to a chat."""
    _, _, chats = await require_services()
    chat = await chats.get_chat(session_id, str(current_user["id"]))
    if chat is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {session_id} not found",
        )

    async with await get_target_database_service(chat) as target_db:
        schema = await target_db.get_compact_database_schema()
    return SchemaResponse(schema=schema)


@app.post("/query", response_model=QueryResponse, tags=["Query Generation"])
async def generate_query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate, validate, execute, and persist a SQL query for a chat."""
    _, llm, chats = await require_services()

    if not request.user_input.strip():
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_INPUT",
            "user_input cannot be empty",
        )

    chat = await chats.get_chat(request.session_id, str(current_user["id"]))
    if chat is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {request.session_id} not found",
        )

    resolved_input = await chats.resolve_pronouns(request.session_id, request.user_input)
    history = await chats.get_recent_messages_for_llm(
        request.session_id,
        str(current_user["id"]),
    )
    next_chat_title = chat["title"]
    if not history:
        next_chat_title = derive_chat_title_from_query(request.user_input)

    async with await get_target_database_service(chat) as target_db:
        schema = await target_db.get_compact_database_schema()
        try:
            sql_query, explanation, _model_used = await llm.generate_sql_query(
                user_input=resolved_input,
                database_schema=schema,
                chat_history=history,
                preferred_model=request.preferred_model or "gemini",
            )
        except Exception as exc:
            logger.exception("LLM query generation failed")
            return QueryResponse(
                session_id=request.session_id,
                title=next_chat_title,
                sql_query="",
                explanation="The assistant could not generate a SQL query.",
                results=[],
                error=to_user_friendly_query_error(str(exc) or "Failed to generate SQL query"),
            )

        if not sql_query:
            return QueryResponse(
                session_id=request.session_id,
                title=next_chat_title,
                sql_query="",
                explanation=explanation or "The assistant could not generate a SQL query.",
                results=[],
                error=to_user_friendly_query_error(explanation or "Could not generate SQL query"),
            )

        is_safe, error_msg = await target_db.is_safe_select_query(sql_query)
        if not is_safe:
            return QueryResponse(
                session_id=request.session_id,
                title=next_chat_title,
                sql_query=sql_query,
                explanation=explanation or "",
                results=[],
                error=to_user_friendly_query_error(f"Query validation failed: {error_msg}"),
            )

        try:
            results = await target_db.execute_select_query(sql_query)
        except Exception as e:
            logger.error("Query execution failed: %s", e)
            return QueryResponse(
                session_id=request.session_id,
                title=next_chat_title,
                sql_query=sql_query,
                explanation=explanation or "",
                results=[],
                error=to_user_friendly_query_error(f"Query execution error: {str(e)}"),
            )

        if results is None:
            return QueryResponse(
                session_id=request.session_id,
                title=next_chat_title,
                sql_query=sql_query,
                explanation=explanation or "",
                results=[],
                error=to_user_friendly_query_error("No results returned"),
            )

    await chats.append_query_message(
        chat_id=request.session_id,
        user_input=resolved_input,
        sql_query=sql_query,
        explanation=explanation or "",
        results=results,
    )
    if not history and next_chat_title != chat["title"]:
        await chats.update_title(request.session_id, next_chat_title)
    await chats.update_last_referenced_table(request.session_id, sql_query)

    return QueryResponse(
        session_id=request.session_id,
        title=next_chat_title,
        sql_query=sql_query,
        explanation=explanation or "",
        results=results,
    )


@app.post("/kpis", response_model=KPIResponse, tags=["KPI Suggestions"])
async def get_kpi_suggestions(
    request: KPIRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate KPI suggestions for the target database linked to a chat."""
    _, llm, chats = await require_services()
    chat = await chats.get_chat(request.session_id, str(current_user["id"]))
    if chat is None:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {request.session_id} not found",
        )

    schema = request.database_schema
    if not schema:
        async with await get_target_database_service(chat) as target_db:
            schema = await target_db.get_compact_database_schema()

    if not schema:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "SCHEMA_UNAVAILABLE",
            "Could not retrieve database schema",
        )

    try:
        kpis, explanation, _model_used = await llm.generate_kpi_suggestions(
            database_schema=schema,
            preferred_model="gemini",
        )
    except Exception as exc:
        logger.exception("LLM KPI generation failed")
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "KPI_GENERATION_FAILED",
            str(exc) or "Failed to generate KPI suggestions",
        )
    normalized_kpis = normalize_kpi_items(kpis)
    if not normalized_kpis:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY,
            "KPI_GENERATION_FAILED",
            explanation or "Failed to generate KPI suggestions",
        )

    return KPIResponse(
        kpis=[
            KPISuggestion(
                number=kpi.get("number", index + 1),
                name=kpi.get("name", ""),
                description=kpi.get("description", ""),
            )
            for index, kpi in enumerate(normalized_kpis[:4])
        ],
        explanation=explanation or "KPI suggestions generated successfully",
    )


@app.delete("/chats/{chat_id}", tags=["Chats"])
async def delete_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a chat and its persisted history."""
    _, _, chats = await require_services()
    deleted = await chats.delete_chat(chat_id, str(current_user["id"]))
    if not deleted:
        raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "CHAT_NOT_FOUND",
            f"Chat {chat_id} not found",
        )
    return {"message": f"Chat {chat_id} deleted"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    detail = exc.detail

    if isinstance(detail, dict):
        error = detail.get("error", "REQUEST_FAILED")
        detail_text = detail.get("detail")
    else:
        error = str(detail or "REQUEST_FAILED")
        detail_text = None

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": error,
            "detail": detail_text,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    logger.error("Unhandled exception: %s", exc)
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
