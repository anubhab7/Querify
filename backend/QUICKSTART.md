# Quick Start Guide

Get Querify API running in 5 minutes.

## Prerequisites

- Python 3.10+
- PostgreSQL database
- API keys: Gemini (Google) & Perplexity

## 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

## 2. Configure Environment

Edit `.env` in the `backend` folder:

```bash
# Copy the example
cp .env.example .env

# Edit with your values
nano .env  # or use your preferred editor
```

**Required values**:
```
DATABASE_URL=postgresql://user:password@localhost:5432/querify_db
GEMINI_API_KEYS=key1,key2,key3
PERPLEXITY_API_KEY=your_api_key_here
```

## 3. Verify Database Connection

```bash
# Test the connection
curl -X POST http://localhost:8000/test-connection
```

Expected response:
```json
{
  "success": true,
  "message": "Database connection successful",
  "database": "querify_db"
}
```

## 4. Start the Server

```bash
# Development mode (with auto-reload)
uvicorn main:app --reload

# Production mode
uvicorn main:app --workers 4
```

API available at: `http://localhost:8000`

## 5. Test the API

### Interactive Docs
Visit: `http://localhost:8000/docs` (Swagger UI)

### Sample Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "How many customers do we have?",
    "preferred_model": "gemini"
  }'
```

### Get KPI Suggestions

```bash
curl -X POST http://localhost:8000/kpis
```

## API Endpoints Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/test-connection` | Test DB connection |
| GET | `/schema` | Get database schema |
| POST | `/query` | Generate SQL from natural language |
| POST | `/kpis` | Get KPI suggestions |
| GET | `/session/{id}` | Retrieve chat session |
| DELETE | `/session/{id}` | Delete chat session |

## Troubleshooting

### "Database connection failed"
- Check `DATABASE_URL` format
- Ensure PostgreSQL is running: `psql -d querify_db`
- Verify network access to DB

### "API key error"
- Verify keys in `.env` are correct
- For Gemini, set `GEMINI_API_KEYS` as a comma-separated list to enable automatic key rotation
- Check Gemini/Perplexity quotas in console
- Ensure no extra whitespace in keys

### "CORS error from frontend"
- Add frontend URL to `CORS_ORIGINS` in `.env`
- Example: `CORS_ORIGINS=http://localhost:3000,http://localhost:8080`

### Import errors
- Ensure you're in `backend` directory
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check `__init__.py` files exist in all directories

## Project Structure Reference

```
backend/
├── main.py              ← FastAPI app (start here)
├── requirements.txt     ← Dependencies
├── .env                 ← Configuration (create from .env.example)
├── models/
│   └── schema.py       ← Data models
└── services/
    ├── database_service.py    ← PostgreSQL
    ├── llm_service.py         ← Gemini & Perplexity
    └── chat_session.py        ← Session management
```

## Next Steps

1. ✅ Start the API server
2. 📝 Create your React frontend
3. 🔗 Connect frontend to API at `http://localhost:8000`
4. 🧪 Test sample queries
5. 🚀 Deploy to production

## API Response Examples

### Successful Query
```json
{
  "session_id": "uuid-xxx",
  "sql_query": "SELECT * FROM customers LIMIT 10",
  "explanation": "This query retrieves the first 10 customer records.",
  "results": [
    {"id": 1, "name": "John Doe", ...},
    {"id": 2, "name": "Jane Smith", ...}
  ]
}
```

### KPI Suggestions
```json
{
  "kpis": [
    {
      "number": 1,
      "name": "Revenue Growth Rate",
      "description": "Quarterly revenue increase percentage"
    },
    ...
  ],
  "explanation": "These KPIs provide..."
}
```

## Support

- Check README.md for detailed documentation
- Review individual service files for implementation details
- Check console logs for error messages

Happy querying! 🚀
