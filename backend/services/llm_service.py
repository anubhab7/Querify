import logging
import json
import os
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import google.generativeai as genai

from models.schema import ChatMessage

logger = logging.getLogger(__name__)

try:
    from google.api_core.exceptions import (
        BadRequest,
        DeadlineExceeded,
        GoogleAPIError,
        InternalServerError,
        PermissionDenied,
        ResourceExhausted,
        ServiceUnavailable,
        TooManyRequests,
        Unauthenticated,
    )
except Exception:  # pragma: no cover - optional import guard
    GoogleAPIError = Exception
    BadRequest = Exception
    DeadlineExceeded = Exception
    InternalServerError = Exception
    PermissionDenied = Exception
    ResourceExhausted = Exception
    ServiceUnavailable = Exception
    TooManyRequests = Exception
    Unauthenticated = Exception


class LLMServiceError(Exception):
    """Raised when an upstream LLM provider returns a usable failure reason."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        self.message = message
        super().__init__(message)


class LLMService:
    """Service for LLM operations with pluggable provider support."""

    def __init__(
        self,
        sarvam_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        perplexity_api_key: Optional[str] = None,
        default_provider: str = "sarvam",
    ):
        """
        Initialize LLM service with API keys.

        Args:
            sarvam_api_key: Sarvam AI API key (from environment if not provided)
            gemini_api_key: Gemini API key (from environment if not provided)
            perplexity_api_key: Perplexity API key (from environment if not provided)
            default_provider: Preferred default provider when client does not specify one
        """
        self.sarvam_api_key = sarvam_api_key or os.getenv("SARVAM_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.perplexity_api_key = perplexity_api_key or os.getenv("PERPLEXITY_API_KEY")

        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)

        self.default_provider = default_provider.strip().lower() or "sarvam"
        self.sarvam_model = os.getenv("SARVAM_MODEL", "sarvam-30b")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.perplexity_model = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
        self.sarvam_endpoint = "https://api.sarvam.ai/v1/chat/completions"
        self.perplexity_endpoint = "https://api.perplexity.ai/chat/completions"
        self.provider_order = ("sarvam", "gemini", "perplexity")
        self.provider_labels = {
            "sarvam": "Sarvam AI",
            "gemini": "Gemini",
            "perplexity": "Perplexity",
        }

        if self.default_provider not in self.provider_order:
            logger.warning(
                "Unsupported default provider '%s'; falling back to sarvam",
                self.default_provider,
            )
            self.default_provider = "sarvam"

    def get_provider_catalog(self) -> Dict[str, Any]:
        """Expose provider metadata for the API/frontend."""
        return {
            "default_provider": self.default_provider,
            "providers": [
                {
                    "id": provider_id,
                    "label": self.provider_labels[provider_id],
                    "configured": self._is_provider_configured(provider_id),
                    "is_default": provider_id == self.default_provider,
                }
                for provider_id in self.provider_order
            ],
        }

    async def generate_sql_query(
        self,
        user_input: str,
        database_schema: str,
        chat_history: Optional[List[ChatMessage]] = None,
        preferred_model: str = "sarvam",
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Generate a SQL query from natural language input.

        Args:
            user_input: Natural language query
            database_schema: Compact database schema
            chat_history: Previous messages for context
            preferred_model: Provider identifier such as 'sarvam' or 'gemini'

        Returns:
            Tuple of (sql_query, explanation, model_used)
            If generation fails, sql_query will be None
        """
        system_prompt = f"""You are a senior analytics engineer. Your task is to convert natural language questions into valid PostgreSQL queries.

DATABASE SCHEMA:
{database_schema}

RULES:
1. Only generate SELECT or WITH (CTE) queries
2. Always provide the SQL query wrapped in <sql></sql> tags
3. Provide a brief explanation in <explanation></explanation> tags
4. If you cannot generate a valid query, respond with <error></error> tags explaining why
5. Only use tables and columns that exist in the schema
6. Prefer explicit column lists instead of SELECT * unless the user explicitly asks for raw rows or all columns
7. Use clear aliases, correct joins, and the right aggregation grain for KPI-style questions
8. Add ORDER BY for rankings and time series when it improves readability
9. Use LIMIT for preview-style requests
10. The user input may be a short KPI title rather than a full sentence; infer the most schema-grounded analytical query without inventing fields

Format your response exactly as:
<sql>
SELECT ...
</sql>
<explanation>
Brief explanation of what the query does
</explanation>"""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if chat_history:
            for msg in chat_history[-6:]:  # Include last 6 messages for context
                messages.append({"role": msg.role.value, "content": msg.content})

        messages.append({"role": "user", "content": user_input})

        result, model_used, error_message = await self._generate_text(messages, preferred_model)

        if result is None or result.strip() == "":
            logger.warning("LLM generation unavailable and no SQL response was returned")
            return (
                None,
                error_message or "The LLM provider did not return a SQL query for this request.",
                model_used,
            )

        # Parse response
        sql_query = self._extract_sql(result)
        explanation = self._extract_explanation(result)

        if sql_query is None:
            logger.warning(f"Could not extract valid SQL from {model_used} response")
            return None, explanation, model_used

        return sql_query, explanation, model_used

    async def generate_kpi_suggestions(
        self,
        database_schema: str,
        preferred_model: str = "sarvam",
    ) -> Tuple[Optional[List[Dict]], Optional[str], str]:
        """
        Generate KPI suggestions based on database schema.

        Args:
            database_schema: Compact database schema
            preferred_model: Provider identifier such as 'sarvam' or 'gemini'

        Returns:
            Tuple of (kpis: List[Dict], explanation: str, model_used: str)
            Each KPI dict has keys: number, name, description
        """
        system_prompt = """You are a business intelligence expert. Analyze the database schema and suggest 4 distinct, meaningful business KPIs.

Requirements:
- Each KPI name must be concise, query-ready, and usable as a standalone analytics prompt.
- Each description must stay on a single line and be one short sentence.
- Prefer KPIs that map directly to SQL using the available schema.
- Do not describe your reasoning, steps, or analysis process.

Return valid JSON only with this exact shape:
{
  "kpis": [
    {"number": 1, "name": "KPI Name", "description": "One-line description"},
    {"number": 2, "name": "KPI Name", "description": "One-line description"},
    {"number": 3, "name": "KPI Name", "description": "One-line description"},
    {"number": 4, "name": "KPI Name", "description": "One-line description"}
  ],
  "explanation": "Brief explanation of how these KPIs work together."
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Database Schema:\n{database_schema}\n\n"
                    "Suggest 4 business KPIs and return JSON only."
                ),
            },
        ]

        result, model_used, error_message = await self._generate_text(messages, preferred_model)

        if result is None or result.strip() == "":
            logger.warning("LLM KPI generation unavailable and no KPI response was returned")
            return (
                None,
                error_message
                or "The LLM provider did not return KPI suggestions for this database.",
                model_used,
            )

        # Parse KPIs and explanation
        kpis = self._parse_kpi_suggestions(result)
        explanation = self._extract_kpi_explanation(result)

        if not kpis or self._has_meta_kpi_content(kpis):
            logger.warning(
                "KPI suggestions from %s were invalid or meta; using heuristic fallback",
                model_used,
            )
            heuristic_kpis, heuristic_explanation = self._generate_kpis_heuristically(
                database_schema
            )
            return heuristic_kpis, heuristic_explanation, model_used

        return kpis, explanation, model_used

    async def _generate_text(
        self,
        messages: List[Dict],
        preferred_model: Optional[str],
    ) -> Tuple[Optional[str], str, Optional[str]]:
        """Attempt text generation using the requested provider and sensible fallbacks."""
        candidates = self._build_provider_candidates(preferred_model)
        last_error: Optional[str] = None
        last_provider = candidates[0] if candidates else self.default_provider

        for provider_id in candidates:
            last_provider = provider_id
            try:
                result = await self._call_llm(provider_id, messages)
            except LLMServiceError as exc:
                logger.error("%s generation failed: %s", exc.provider, exc.message)
                last_error = exc.message
                continue
            except Exception as exc:
                logger.exception("Unexpected %s generation failure", provider_id)
                last_error = self._extract_provider_error(exc)
                continue

            if result and result.strip():
                return result.strip(), provider_id, None

            last_error = (
                f"{self.provider_labels.get(provider_id, provider_id)} returned an empty response."
            )

        return None, last_provider, last_error

    def _build_provider_candidates(self, preferred_model: Optional[str]) -> List[str]:
        """Choose the ordered list of providers to try for this request."""
        requested = (preferred_model or self.default_provider).strip().lower()
        if requested not in self.provider_order:
            raise LLMServiceError(
                requested,
                f"Unsupported LLM provider '{requested}'.",
            )

        candidates = [requested]
        if self.default_provider not in candidates:
            candidates.append(self.default_provider)

        for provider_id in self.provider_order:
            if provider_id in candidates or not self._is_provider_configured(provider_id):
                continue
            candidates.append(provider_id)

        return candidates

    async def _call_llm(self, model: str, messages: List[Dict]) -> Optional[str]:
        """
        Call the configured LLM provider.

        Args:
            model: Provider identifier
            messages: List of message dicts with role and content

        Returns:
            LLM response or None if failed
        """
        if model == "sarvam":
            return await self._call_sarvam(messages)
        if model == "gemini":
            return await self._call_gemini(messages)
        if model == "perplexity":
            return await self._call_perplexity(messages)

        raise LLMServiceError(model, f"Unsupported LLM provider '{model}'.")

    def _is_provider_configured(self, provider_id: str) -> bool:
        """Check whether a provider has the credentials it needs."""
        api_keys = {
            "sarvam": self.sarvam_api_key,
            "gemini": self.gemini_api_key,
            "perplexity": self.perplexity_api_key,
        }
        return bool(api_keys.get(provider_id))

    async def _call_sarvam(self, messages: List[Dict]) -> Optional[str]:
        """Call Sarvam AI's chat completions API."""
        if not self.sarvam_api_key:
            raise LLMServiceError("sarvam", "Sarvam AI API key not configured")

        headers = {
            "Authorization": f"Bearer {self.sarvam_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.sarvam_model,
            "messages": self._normalize_chat_messages(messages),
            "temperature": 0.2,
            "max_tokens": 2048,
            "reasoning_effort": "medium",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.sarvam_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as response:
                    if response.status != 200:
                        error_payload = await response.text()
                        raise LLMServiceError(
                            "sarvam",
                            self._format_provider_error(
                                "sarvam",
                                Exception(error_payload),
                                status_code=response.status,
                                default="Sarvam AI request failed.",
                            ),
                        )

                    data = await response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise LLMServiceError(
                            "sarvam",
                            "Sarvam AI returned an empty response for this request.",
                        )

                    message = choices[0].get("message", {})
                    content = (
                        (message.get("content") or "").strip()
                        or (message.get("reasoning_content") or "").strip()
                    )
                    if content:
                        return content

                    raise LLMServiceError(
                        "sarvam",
                        "Sarvam AI returned an empty response for this request.",
                    )
        except asyncio.TimeoutError as exc:
            raise LLMServiceError(
                "sarvam",
                self._format_provider_error(
                    "sarvam",
                    exc,
                    status_code=504,
                    default="Sarvam AI request timed out. Please try again.",
                ),
            ) from exc
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(
                "sarvam",
                self._format_provider_error("sarvam", exc),
            ) from exc

    async def _call_gemini(self, messages: List[Dict]) -> Optional[str]:
        """
        Call Gemini API.

        Args:
            messages: List of message dicts

        Returns:
            Response text or None
        """
        if not self.gemini_api_key:
            raise LLMServiceError("gemini", "Gemini API key not configured")

        try:
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "user").upper()
                prompt_parts.append(f"{role}:\n{msg.get('content', '')}")

            model = genai.GenerativeModel(self.gemini_model)
            response = model.generate_content(
                "\n\n".join(prompt_parts),
                stream=False,
            )

            if response and response.text:
                return response.text.strip()

            raise LLMServiceError(
                "gemini", "Gemini returned an empty response for this request."
            )

        except LLMServiceError:
            raise
        except (ResourceExhausted, TooManyRequests) as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error(
                    "gemini",
                    exc,
                    default="Gemini API usage limit reached. Please try again shortly.",
                ),
            ) from exc
        except (Unauthenticated, PermissionDenied) as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error(
                    "gemini",
                    exc,
                    default="Gemini API authentication failed. Please verify the configured API key and permissions.",
                ),
            ) from exc
        except (DeadlineExceeded, asyncio.TimeoutError) as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error(
                    "gemini",
                    exc,
                    default="Gemini API request timed out. Please try again.",
                ),
            ) from exc
        except (ServiceUnavailable, InternalServerError) as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error(
                    "gemini",
                    exc,
                    default="Gemini API is temporarily unavailable. Please try again shortly.",
                ),
            ) from exc
        except BadRequest as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error(
                    "gemini",
                    exc,
                    default="Gemini API rejected this request. Please try again with a different prompt.",
                ),
            ) from exc
        except GoogleAPIError as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error("gemini", exc),
            ) from exc
        except Exception as exc:
            raise LLMServiceError(
                "gemini",
                self._format_provider_error("gemini", exc),
            ) from exc

    @classmethod
    def _format_provider_error(
        cls,
        provider: str,
        exc: Exception,
        status_code: Optional[int] = None,
        default: Optional[str] = None,
    ) -> str:
        """Normalize provider failures without overfitting to one vendor."""
        error_text = cls._extract_provider_error(exc)
        lowered = error_text.lower()
        resolved_status = (
            status_code
            or getattr(exc, "code", None)
            or getattr(exc, "status_code", None)
        )
        provider_label = {
            "sarvam": "Sarvam AI",
            "gemini": "Gemini",
            "perplexity": "Perplexity",
        }.get(provider, provider)

        rate_limit_markers = (
            "resource exhausted",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
            "429",
            "exceeded your current quota",
        )
        auth_markers = (
            "api key",
            "permission denied",
            "permission_denied",
            "unauthorized",
            "unauthenticated",
            "authentication",
            "credential",
        )
        timeout_markers = ("timeout", "timed out", "deadline exceeded", "deadline_exceeded")
        unavailable_markers = (
            "service unavailable",
            "temporarily unavailable",
            "unavailable",
            "internal error",
            "backend error",
            "overloaded",
        )
        bad_request_markers = (
            "invalid argument",
            "bad request",
            "invalid",
            "unsupported",
            "blocked",
        )

        if resolved_status == 429 or any(marker in lowered for marker in rate_limit_markers):
            return f"{provider_label} API usage limit reached. Please try again shortly."
        if resolved_status in {401, 403} or any(marker in lowered for marker in auth_markers):
            return (
                f"{provider_label} API authentication failed. "
                "Please verify the configured API key and permissions."
            )
        if resolved_status == 504 or any(marker in lowered for marker in timeout_markers):
            return f"{provider_label} API request timed out. Please try again."
        if resolved_status in {500, 502, 503} or any(
            marker in lowered for marker in unavailable_markers
        ):
            return f"{provider_label} API is temporarily unavailable. Please try again shortly."
        if resolved_status == 400 or any(marker in lowered for marker in bad_request_markers):
            return error_text or f"{provider_label} API rejected this request."

        return error_text or default or f"{provider_label} API request failed."

    async def _call_perplexity(self, messages: List[Dict]) -> Optional[str]:
        """
        Call Perplexity API.

        Args:
            messages: List of message dicts

        Returns:
            Response text or None
        """
        if not self.perplexity_api_key:
            raise LLMServiceError("perplexity", "Perplexity API key not configured")

        try:
            # Normalize messages for Perplexity
            normalized_messages = self._normalize_for_perplexity(messages)

            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.perplexity_model,
                "messages": normalized_messages,
                "max_tokens": 2048,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.perplexity_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("choices") and len(data["choices"]) > 0:
                            return (
                                data["choices"][0]
                                .get("message", {})
                                .get("content", "")
                                .strip()
                            )
                    else:
                        error_payload = await response.text()
                        raise LLMServiceError(
                            "perplexity",
                            self._format_provider_error(
                                "perplexity",
                                Exception(error_payload),
                                status_code=response.status,
                                default="Perplexity API request failed.",
                            ),
                        )

        except asyncio.TimeoutError:
            raise LLMServiceError(
                "perplexity", "Perplexity API request timed out."
            ) from None
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(
                "perplexity", self._extract_provider_error(exc)
            ) from exc

        return None

    @staticmethod
    def _normalize_chat_messages(messages: List[Dict]) -> List[Dict]:
        """Normalize outbound chat messages for providers that follow OpenAI-style schemas."""
        normalized: List[Dict] = []
        for msg in messages:
            role = str(msg.get("role", "user")).lower()
            if role not in {"system", "user", "assistant"}:
                role = "user"

            normalized.append(
                {
                    "role": role,
                    "content": str(msg.get("content", "")).strip(),
                }
            )
        return normalized

    @staticmethod
    def _extract_provider_error(exc: Exception) -> str:
        """Best-effort extraction of a concise upstream provider failure reason."""
        candidates: List[str] = []

        for value in (
            getattr(exc, "message", None),
            getattr(exc, "details", None),
            str(exc),
        ):
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())

        response = getattr(exc, "response", None)
        if response is not None:
            response_text = getattr(response, "text", None)
            if isinstance(response_text, str) and response_text.strip():
                candidates.append(response_text.strip())

        for candidate in candidates:
            message_match = re.search(
                r'"message"\s*:\s*"([^"]+)"',
                candidate,
                flags=re.IGNORECASE,
            )
            if message_match:
                return message_match.group(1).strip()

            details_match = re.search(
                r"details\s*=\s*['\"]([^'\"]+)['\"]",
                candidate,
                flags=re.IGNORECASE,
            )
            if details_match:
                return details_match.group(1).strip()

            cleaned = re.sub(r"\s+", " ", candidate).strip(" :")
            if cleaned:
                return cleaned

        return "The LLM provider request failed."

    @staticmethod
    def _parse_schema(database_schema: str) -> List[Dict[str, object]]:
        """Parse compact schema into table metadata."""
        tables: List[Dict[str, object]] = []
        for raw_line in database_schema.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line or "." not in line:
                continue

            table_ref, columns_raw = line.split(":", 1)
            schema_name, table_name = table_ref.strip().split(".", 1)
            columns = [col.strip() for col in columns_raw.split(",") if col.strip()]
            tables.append(
                {
                    "schema": schema_name,
                    "table": table_name,
                    "full_name": f"{schema_name}.{table_name}",
                    "columns": columns,
                }
            )
        return tables

    @staticmethod
    def _find_table_candidates(
        user_input: str, tables: List[Dict[str, object]]
    ) -> List[Dict[str, object]]:
        """Find tables referenced in the user input."""
        normalized_input = re.sub(r"[^a-z0-9_ ]+", " ", user_input.lower())
        candidates = []

        for table in tables:
            table_name = str(table["table"]).lower()
            singular_name = table_name[:-1] if table_name.endswith("s") else table_name
            patterns = [
                rf"\b{re.escape(table_name)}\b",
                rf"\b{re.escape(singular_name)}\b",
            ]
            if any(re.search(pattern, normalized_input) for pattern in patterns):
                candidates.append(table)

        return candidates

    @staticmethod
    def _find_column(
        columns: List[str], keywords: List[str], preferred_suffixes: Optional[List[str]] = None
    ) -> Optional[str]:
        """Find a column matching any keyword and optional suffix preference."""
        preferred_suffixes = preferred_suffixes or []
        lowered = [(column, column.lower()) for column in columns]

        for keyword in keywords:
            for column, lower_column in lowered:
                if keyword in lower_column:
                    if not preferred_suffixes or any(
                        lower_column.endswith(suffix) for suffix in preferred_suffixes
                    ):
                        return column

        for keyword in keywords:
            for column, lower_column in lowered:
                if keyword in lower_column:
                    return column

        return None

    def _generate_query_heuristically(
        self,
        user_input: str,
        database_schema: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Generate a conservative SQL query for common analytics prompts."""
        tables = self._parse_schema(database_schema)
        normalized_input = re.sub(r"\s+", " ", user_input.strip().lower())

        if not tables:
            return None, "No usable schema information was available."

        if re.search(r"\bhow many tables\b|\bnumber of tables\b|\bcount tables\b", normalized_input):
            return (
                "SELECT COUNT(*) AS table_count "
                "FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema');",
                "Counts all non-system tables available in the database.",
            )

        candidates = self._find_table_candidates(normalized_input, tables)
        table = candidates[0] if candidates else tables[0]
        full_name = str(table["full_name"])
        columns = list(table["columns"])

        count_alias = f"{table['table']}_count"
        if re.search(r"\bhow many\b|\bcount\b|\bnumber of\b", normalized_input):
            return (
                f"SELECT COUNT(*) AS {count_alias} FROM {full_name};",
                f"Counts the total number of rows in {full_name}.",
            )

        limit_match = re.search(r"\btop\s+(\d+)\b|\blimit\s+(\d+)\b|\bfirst\s+(\d+)\b", normalized_input)
        limit = next((int(group) for group in limit_match.groups() if group), 10) if limit_match else 10

        sort_column = None
        sort_keywords = [
            "price",
            "amount",
            "total",
            "count",
            "date",
            "created",
            "travel",
            "start",
            "end",
        ]
        if re.search(r"\btop\b|\bhighest\b|\blargest\b|\bbiggest\b|\bmost\b", normalized_input):
            sort_column = self._find_column(columns, sort_keywords)
            if sort_column:
                return (
                    f"SELECT * FROM {full_name} ORDER BY {sort_column} DESC LIMIT {limit};",
                    f"Returns the top {limit} rows from {full_name} ordered by {sort_column} descending.",
                )

        if re.search(r"\blatest\b|\brecent\b|\bnewest\b", normalized_input):
            sort_column = self._find_column(columns, ["date", "created", "paid", "start", "end"])
            if sort_column:
                return (
                    f"SELECT * FROM {full_name} ORDER BY {sort_column} DESC LIMIT {limit};",
                    f"Returns the most recent {limit} rows from {full_name} based on {sort_column}.",
                )

        if re.search(r"\bshow\b|\blist\b|\bget\b|\bdisplay\b", normalized_input):
            return (
                f"SELECT * FROM {full_name} LIMIT {limit};",
                f"Returns up to {limit} rows from {full_name}.",
            )

        return (
            f"SELECT * FROM {full_name} LIMIT {limit};",
            f"Generated a safe default query for {full_name} because the LLM provider was unavailable.",
        )

    def _generate_kpis_heuristically(
        self,
        database_schema: str,
    ) -> Tuple[List[Dict], str]:
        """Generate schema-aware KPI suggestions without an LLM."""
        tables = self._parse_schema(database_schema)
        full_names = {str(table["table"]): str(table["full_name"]) for table in tables}

        kpis: List[Dict] = []

        if "bookings" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Total Bookings",
                    "description": f"Track booking volume trends from {full_names['bookings']}.",
                }
            )
        if "payments" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Payment Collection Value",
                    "description": f"Measure realized revenue from {full_names['payments']}.",
                }
            )
        if "trips" in full_names and "bookings" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Trip Utilization",
                    "description": f"Compare bookings and capacity across {full_names['trips']}.",
                }
            )
        if "customers" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "New Customer Acquisition",
                    "description": f"Measure customer growth from {full_names['customers']}.",
                }
            )
        if "destinations" in full_names and "trips" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Destination Performance",
                    "description": "See which destinations drive the most trip activity.",
                }
            )

        while len(kpis) < 4:
            table = tables[len(kpis) % len(tables)]
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": f"{table['table'].replace('_', ' ').title()} Activity",
                    "description": f"Track recent activity in {table['full_name']}.",
                }
            )

        explanation = (
            "These KPI suggestions are derived directly from the available schema, "
            "so the endpoint remains useful even when external LLM providers are unavailable."
        )
        return kpis[:4], explanation

    @staticmethod
    def _normalize_for_perplexity(messages: List[Dict]) -> List[Dict]:
        """
        Normalize messages for Perplexity API.

        Ensures strict alternation between user and assistant after system message.

        Args:
            messages: Original message list

        Returns:
            Normalized message list
        """
        if not messages:
            return []

        normalized = []
        last_role = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                normalized.append(msg)
                last_role = "system"
            else:
                # Convert assistant to model role for Perplexity if needed
                perp_role = "assistant" if role == "assistant" else "user"

                # Skip duplicate consecutive roles
                if perp_role != last_role or last_role == "system":
                    normalized.append(
                        {"role": perp_role, "content": content}
                    )
                    last_role = perp_role

        return normalized

    @staticmethod
    def _extract_sql(response: str) -> Optional[str]:
        """Extract SQL query from response wrapped in <sql> tags."""
        try:
            start = response.find("<sql>")
            end = response.find("</sql>")

            if start != -1 and end != -1:
                sql = response[start + 5 : end].strip()
                return sql if sql else None

            return None
        except Exception as e:
            logger.error(f"Error extracting SQL: {e}")
            return None

    @staticmethod
    def _extract_explanation(response: str) -> Optional[str]:
        """Extract explanation from response wrapped in <explanation> tags."""
        try:
            start = response.find("<explanation>")
            end = response.find("</explanation>")

            if start != -1 and end != -1:
                explanation = response[start + 13 : end].strip()
                return explanation if explanation else None

            return None
        except Exception as e:
            logger.error(f"Error extracting explanation: {e}")
            return None

    @staticmethod
    def _parse_kpi_suggestions(response: str) -> Optional[List[Dict[str, Any]]]:
        """
        Parse KPI suggestions from JSON or numbered list format.

        Accepted examples:
        - [{"number": 1, "name": "...", "description": "..."}]
        - {"kpis": [...]}
        - 1. KPI Name: Description
        """
        try:
            json_payload = LLMService._extract_json_payload(response)
            if json_payload is not None:
                if isinstance(json_payload, dict):
                    candidate_items = json_payload.get("kpis")
                else:
                    candidate_items = json_payload

                if isinstance(candidate_items, list):
                    parsed_from_json = []
                    for index, item in enumerate(candidate_items, start=1):
                        normalized_item = LLMService._coerce_kpi_item(item, index=index)
                        if normalized_item is not None:
                            parsed_from_json.append(normalized_item)
                    if parsed_from_json:
                        return parsed_from_json

            lines = response.splitlines()
            numbered_kpis: List[Dict[str, Any]] = []

            for line in lines:
                stripped = line.strip().strip("*").strip()
                if not stripped:
                    continue

                match = re.match(
                    r"^(?P<number>\d+)[\.\)]\s*(?P<body>.+)$",
                    stripped,
                )
                if not match:
                    continue

                number = int(match.group("number"))
                body = match.group("body").strip()

                if ":" in body:
                    name, description = body.split(":", 1)
                elif " - " in body:
                    name, description = body.split(" - ", 1)
                else:
                    name, description = body, body

                normalized_item = LLMService._coerce_kpi_item(
                    {
                        "number": number,
                        "name": name.strip(),
                        "description": description.strip(),
                    },
                    index=number,
                )
                if normalized_item is not None:
                    numbered_kpis.append(normalized_item)

            return numbered_kpis if numbered_kpis else None

        except Exception as e:
            logger.error(f"Error parsing KPI suggestions: {e}")
            return None

    @staticmethod
    def _extract_json_payload(response: str) -> Optional[Any]:
        """Extract a JSON object or array from a raw LLM response."""
        candidates = [response.strip()]

        fenced_match = re.search(r"```(?:json)?\s*(.*?)```", response, flags=re.DOTALL)
        if fenced_match:
            candidates.insert(0, fenced_match.group(1).strip())

        bracket_match = re.search(r"(\[\s*{.*}\s*]|\{\s*\".*\})", response, flags=re.DOTALL)
        if bracket_match:
            candidates.append(bracket_match.group(1).strip())

        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _coerce_kpi_item(item: Any, index: int) -> Optional[Dict[str, Any]]:
        """Normalize one KPI item into the API's expected dictionary shape."""
        def clean_label(value: str) -> str:
            return re.sub(r"[*_`]+", "", value).strip(" :.-").strip()

        if isinstance(item, str):
            stripped = item.strip()
            if not stripped:
                return None
            if ":" in stripped:
                name, description = stripped.split(":", 1)
            elif " - " in stripped:
                name, description = stripped.split(" - ", 1)
            else:
                name, description = stripped, stripped
            cleaned_name = clean_label(name)
            cleaned_description = LLMService._to_single_line_kpi_description(
                clean_label(description)
            )
            if cleaned_name.lower() in {"kpi", "kpi name", "name"} and cleaned_description:
                cleaned_name = cleaned_description
            return {
                "number": index,
                "name": cleaned_name,
                "description": cleaned_description or cleaned_name,
            }

        if not isinstance(item, dict):
            return None

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
        description = LLMService._to_single_line_kpi_description(description)
        if not name:
            return None

        raw_number = item.get("number", index)
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            number = index

        return {
            "number": number,
            "name": name,
            "description": description,
        }

    @staticmethod
    def _to_single_line_kpi_description(
        description: str,
        *,
        max_length: int = 110,
    ) -> str:
        """Collapse verbose KPI descriptions into a short single-line summary."""
        normalized = re.sub(r"\s+", " ", (description or "")).strip(" :.-").strip()
        if not normalized:
            return ""

        sentence_match = re.match(r"^(.+?[.!?])(?:\s|$)", normalized)
        if sentence_match:
            normalized = sentence_match.group(1).strip()

        if len(normalized) <= max_length:
            return normalized

        shortened = normalized[: max_length - 3].rsplit(" ", 1)[0].strip(" ,;:-")
        return f"{shortened or normalized[: max_length - 3].strip()}..."

    @staticmethod
    def _has_meta_kpi_content(kpis: List[Dict[str, Any]]) -> bool:
        """Reject KPI lists that are really planning steps or prompt analysis."""
        meta_markers = (
            "deconstruct",
            "analyze the database schema",
            "brainstorm",
            "selecting the final",
            "request",
            "schema",
            "reasoning",
            "requirements",
            "output format",
        )
        flagged = 0

        for item in kpis:
            combined = " ".join(
                [
                    str(item.get("name", "")),
                    str(item.get("description", "")),
                ]
            ).lower()
            if any(marker in combined for marker in meta_markers):
                flagged += 1

        return flagged >= 2

    @staticmethod
    def _extract_kpi_explanation(response: str) -> Optional[str]:
        """Extract explanation section from KPI response (after numbered list)."""
        try:
            json_payload = LLMService._extract_json_payload(response)
            if isinstance(json_payload, dict):
                explanation = str(json_payload.get("explanation") or "").strip()
                if explanation:
                    return explanation

            lines = response.split("\n")
            explanation_lines = []
            found_explanation = False

            for line in lines:
                # Skip numbered list items
                if line.strip() and line.strip()[0].isdigit() and "." in line:
                    continue

                # Collect other lines as explanation
                if line.strip():
                    found_explanation = True
                    explanation_lines.append(line.strip())

            return " ".join(explanation_lines) if explanation_lines else None

        except Exception as e:
            logger.error(f"Error extracting KPI explanation: {e}")
            return None
