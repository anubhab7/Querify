# Querify API - Python FastAPI Backend

Convert Natural Language to PostgreSQL queries using LLMs (Gemini & Perplexity)

## Project Structure

```
backend/
├── main.py                          # FastAPI application with routes
├── requirements.txt                 # Python dependencies
├── .env.example                     # Example environment configuration
├── models/
│   ├── __init__.py
│   └── schema.py                   # Pydantic models for requests/responses
└── services/
    ├── __init__.py
    ├── database_service.py         # PostgreSQL operations & query validation
    ├── llm_service.py              # Gemini & Perplexity API integration
    └── chat_session.py             # Session management & pronoun resolution
```

## Features

### 🗄️ Database Service (`services/database_service.py`)
- **`get_compact_database_schema()`** - Returns schema in compact format: `schema.table: col1, col2`
- **`get_column_value_samples()`** - Fetches distinct values for text columns
- **`is_safe_select_query()`** - Validates queries (only SELECT/WITH allowed, blocks INSERT/UPDATE/DROP/etc.)
- **`execute_select_query()`** - Safely executes validated queries
- **`test_connection()`** - Health check for database connectivity

### 🤖 LLM Service (`services/llm_service.py`)
- **Gemini Integration** - Uses `gemini-2.0-flash` model
- **Perplexity Integration** - Uses `sonar-pro` model
- **Fallback Logic** - Automatically tries alternate model if preferred fails
- **Message Normalization** - Ensures strict user/assistant alternation for Perplexity
- **SQL Query Generation** - Converts natural language to SQL
- **KPI Suggestions** - Suggests 4 business KPIs from schema

### 💬 Chat Session (`services/chat_session.py`)
- **Conversation History** - Maintains last 8 messages per session
- **Pronoun Resolution** - Replaces "it", "that table", "the table", "this table" with last referenced table
- **Context Extraction** - Automatically tracks table references from SQL queries
- **Session Management** - Creates, retrieves, and manages multiple chat sessions

### 📡 FastAPI Endpoints

#### Health & Connection
- `GET /health` - Health check
- `POST /test-connection` - Test database connection
- `POST /database/connect` - Test a user-supplied PostgreSQL connection without changing the app's default database

#### Database Schema
- `GET /schema` - Get compact database schema

#### Query Generation
- `POST /query` - Generate SQL query from natural language
  - Input: `user_input`, optional `session_id`, `preferred_model`
  - Output: `sql_query`, `explanation`, `results`, `session_id`

#### KPI Suggestions
- `POST /kpis` - Get 4 business KPI suggestions
  - Input: optional `database_schema`
  - Output: List of KPIs with descriptions

#### Session Management
- `GET /session/{session_id}` - Retrieve chat session data
- `DELETE /session/{session_id}` - Delete a chat session

## Setup Instructions

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env` with:
- `DATABASE_URL` - PostgreSQL connection string
- `GEMINI_API_KEY` - Your Gemini API key
- `PERPLEXITY_API_KEY` - Your Perplexity API key
- `CORS_ORIGINS` - Frontend URL(s)

### 3. Run the Server

```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at `http://localhost:8000`

## API Usage Examples

### Test Connection
```bash
curl -X POST http://localhost:8000/test-connection
```

### Test Custom PostgreSQL Credentials
```bash
curl -X POST http://localhost:8000/database/connect \
  -H "Content-Type: application/json" \
  -d '{
    "host": "your-db-host",
    "port": 5432,
    "database": "your_database",
    "username": "your_user",
    "password": "your_password",
    "ssl": true
  }'
```

### Get Schema
```bash
curl http://localhost:8000/schema
```

### Generate Query
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "Show me the top 10 customers by total sales",
    "preferred_model": "gemini"
  }'
```

### Get KPI Suggestions
```bash
curl -X POST http://localhost:8000/kpis
```

### Retrieve Session
```bash
curl http://localhost:8000/session/{session_id}
```

## Query Safety Features

The `is_safe_select_query()` function ensures security by:

1. **Keyword Blocking**: Rejects INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, EXECUTE, PRAGMA, COMMIT, ROLLBACK
2. **SQL Parsing**: Uses `sqlparse` to validate query structure
3. **Identifier Validation**: Prevents SQL injection via regex validation
4. **Statement Restriction**: Only allows SELECT and WITH (CTE) statements

## Pronoun Resolution Examples

When a user has previously asked about a table, pronouns are automatically resolved:

```
User: "Show me all customers"
→ LLM generates: SELECT * FROM public.customers

User: "How many records in it?"
→ Resolved to: "How many records in public.customers?"
```

Supported pronouns:
- "it"
- "that table"
- "the table"
- "this table"

## Message Flow for Perplexity

The service automatically normalizes messages for Perplexity API to ensure:
1. System message is first (if present)
2. Strict alternation between user and assistant messages
3. No duplicate consecutive roles

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DATABASE_URL | Yes | - | PostgreSQL connection string |
| GEMINI_API_KEY | Yes | - | Google Gemini API key |
| PERPLEXITY_API_KEY | Yes | - | Perplexity API key |
| API_HOST | No | 0.0.0.0 | Server host |
| API_PORT | No | 8000 | Server port |
| API_DEBUG | No | false | Debug mode |
| CORS_ORIGINS | No | localhost:3000 | Allowed CORS origins |
| MAX_HISTORY_MESSAGES | No | 8 | Max messages per session |

## Error Handling

All endpoints return structured error responses:

```json
{
  "error": "Error message",
  "detail": "Additional details (if available)",
  "status_code": 400
}
```

Common `/database/connect` error codes:
- `INVALID_CREDENTIALS` - Username or password is incorrect
- `DATABASE_NOT_FOUND` - The target database does not exist
- `INSUFFICIENT_PRIVILEGES` - The user cannot access the requested database
- `HOST_RESOLUTION_FAILED` - The hostname could not be resolved
- `CONNECTION_REFUSED` - The server refused the connection
- `CONNECTION_TIMEOUT` - The server did not respond in time
- `SSL_REQUIRED` - The server requires SSL, so retry with `"ssl": true`
- `SSL_ERROR` - The submitted SSL settings were rejected by the server
- `TOO_MANY_CONNECTIONS` - The PostgreSQL server has reached its client limit

## Performance Considerations

- **Connection Pooling**: asyncpg connection pool for efficient DB access
- **Async Operations**: All I/O operations are async for concurrency
- **Session Timeout**: Sessions expire after 60 minutes of inactivity
- **Message History**: Limited to last 8 messages to reduce token usage

## Development Workflow

1. Test database connection first
2. Retrieve schema to understand data structure
3. Use `/query` endpoint with sample questions
4. Use `/kpis` endpoint to get business insights
5. Manage sessions with `/session/{id}` endpoints

## Notes

- All SQL queries are validated before execution
- LLM responses are parsed for structured output (SQL, explanations)
- Fallback logic ensures reliability even if one LLM service fails
- Sessions are automatically cleaned up after timeout
- CORS middleware allows frontend integration

## Troubleshooting

### Database Connection Failed
- Verify `DATABASE_URL` in `.env`
- Ensure PostgreSQL server is running
- Check network connectivity

### API Key Errors
- Verify `GEMINI_API_KEY` and `PERPLEXITY_API_KEY` are valid
- Check API key permissions/quotas
- Ensure keys are properly set in `.env`

### CORS Issues
- Add frontend URL to `CORS_ORIGINS` in `.env`
- Format: `http://localhost:3000` (no trailing slash)

## Future Enhancements

- [ ] Database backup/recovery features
- [ ] Query result caching
- [ ] Advanced analytics on usage patterns
- [ ] Support for additional LLM providers
- [ ] Query performance optimization suggestions
