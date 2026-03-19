"""
LLM Service for orchestrating Gemini and Perplexity API calls.
Handles message normalization, fallback logic, and context-aware query generation.
"""

import os
import logging
import re
from typing import Optional, List, Dict, Tuple
import google.generativeai as genai
import aiohttp
import asyncio
from models.schema import ChatMessage, MessageRole

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM operations with Gemini and Perplexity support."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        perplexity_api_key: Optional[str] = None,
    ):
        """
        Initialize LLM service with API keys.

        Args:
            gemini_api_key: Gemini API key (from environment if not provided)
            perplexity_api_key: Perplexity API key (from environment if not provided)
        """
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.perplexity_api_key = perplexity_api_key or os.getenv(
            "PERPLEXITY_API_KEY"
        )

        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)

        self.gemini_model = "gemini-2.0-flash"
        self.perplexity_model = "sonar-pro"
        self.perplexity_endpoint = "https://api.perplexity.ai/chat/completions"

    async def generate_sql_query(
        self,
        user_input: str,
        database_schema: str,
        chat_history: Optional[List[ChatMessage]] = None,
        preferred_model: str = "gemini",
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Generate a SQL query from natural language input.

        Args:
            user_input: Natural language query
            database_schema: Compact database schema
            chat_history: Previous messages for context
            preferred_model: 'gemini' or 'perplexity'

        Returns:
            Tuple of (sql_query, explanation, model_used)
            If generation fails, sql_query will be None
        """
        system_prompt = f"""You are a SQL query generator. Your task is to convert natural language questions into valid PostgreSQL queries.

DATABASE SCHEMA:
{database_schema}

RULES:
1. Only generate SELECT or WITH (CTE) queries
2. Always provide the SQL query wrapped in <sql></sql> tags
3. Provide a brief explanation in <explanation></explanation> tags
4. If you cannot generate a valid query, respond with <error></error> tags explaining why

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

        # Try preferred model first, but skip Perplexity if it is unavailable or expired.
        model_used = preferred_model
        result = await self._call_llm(preferred_model, messages)

        if (result is None or result.strip() == "") and preferred_model != "gemini":
            logger.warning(
                f"Preferred model {preferred_model} failed, attempting fallback gemini"
            )
            model_used = "gemini"
            result = await self._call_llm("gemini", messages)

        if result is None or result.strip() == "":
            logger.warning("LLM generation unavailable, using heuristic SQL fallback")
            sql_query, explanation = self._generate_query_heuristically(
                user_input=user_input,
                database_schema=database_schema,
            )
            return sql_query, explanation, "heuristic"

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
        preferred_model: str = "gemini",
    ) -> Tuple[Optional[List[Dict]], Optional[str], str]:
        """
        Generate KPI suggestions based on database schema.

        Args:
            database_schema: Compact database schema
            preferred_model: 'gemini' or 'perplexity'

        Returns:
            Tuple of (kpis: List[Dict], explanation: str, model_used: str)
            Each KPI dict has keys: number, name, description
        """
        system_prompt = """You are a business intelligence expert. Analyze the database schema and suggest 4 distinct, meaningful business KPIs.

Format your response as a numbered list with clear descriptions:
1. KPI Name: Description focusing on business value
2. KPI Name: Description focusing on business value
3. KPI Name: Description focusing on business value
4. KPI Name: Description focusing on business value

After the list, provide a brief explanation of how these KPIs work together."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Database Schema:\n{database_schema}\n\nSuggest 4 business KPIs.",
            },
        ]

        # Try preferred model first, but skip Perplexity if it is unavailable or expired.
        model_used = preferred_model
        result = await self._call_llm(preferred_model, messages)

        if (result is None or result.strip() == "") and preferred_model != "gemini":
            logger.warning(
                f"Preferred model {preferred_model} failed, attempting fallback gemini"
            )
            model_used = "gemini"
            result = await self._call_llm("gemini", messages)

        if result is None or result.strip() == "":
            logger.warning("LLM KPI generation unavailable, using heuristic KPI fallback")
            kpis, explanation = self._generate_kpis_heuristically(database_schema)
            return kpis, explanation, "heuristic"

        # Parse KPIs and explanation
        kpis = self._parse_kpi_suggestions(result)
        explanation = self._extract_kpi_explanation(result)

        return kpis, explanation, model_used

    async def _call_llm(self, model: str, messages: List[Dict]) -> Optional[str]:
        """
        Call LLM API (Gemini or Perplexity).

        Args:
            model: 'gemini' or 'perplexity'
            messages: List of message dicts with role and content

        Returns:
            LLM response or None if failed
        """
        try:
            if model == "gemini":
                return await self._call_gemini(messages)
            elif model == "perplexity":
                return await self._call_perplexity(messages)
            else:
                logger.error(f"Unknown model: {model}")
                return None
        except Exception as e:
            logger.error(f"Error calling {model}: {e}")
            return None

    async def _call_gemini(self, messages: List[Dict]) -> Optional[str]:
        """
        Call Gemini API.

        Args:
            messages: List of message dicts

        Returns:
            Response text or None
        """
        if not self.gemini_api_key:
            logger.error("Gemini API key not configured")
            return None

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

            return None

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None

    async def _call_perplexity(self, messages: List[Dict]) -> Optional[str]:
        """
        Call Perplexity API.

        Args:
            messages: List of message dicts

        Returns:
            Response text or None
        """
        if not self.perplexity_api_key:
            logger.error("Perplexity API key not configured")
            return None

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
                        logger.error(f"Perplexity API error: {response.status}")
                        return None

        except asyncio.TimeoutError:
            logger.error("Perplexity API request timeout")
            return None
        except Exception as e:
            logger.error(f"Perplexity API error: {e}")
            return None

        return None

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
                    "description": f"Track booking volume over time from {full_names['bookings']} to monitor sales activity.",
                }
            )
        if "payments" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Payment Collection Value",
                    "description": f"Sum payment amounts in {full_names['payments']} to measure realized revenue.",
                }
            )
        if "trips" in full_names and "bookings" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Trip Utilization",
                    "description": f"Compare booking counts in {full_names['bookings']} against trip capacity in {full_names['trips']} to identify underbooked or full trips.",
                }
            )
        if "customers" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "New Customer Acquisition",
                    "description": f"Measure how many customers are added over time using {full_names['customers']}.",
                }
            )
        if "destinations" in full_names and "trips" in full_names:
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": "Destination Performance",
                    "description": f"Join {full_names['trips']} with {full_names['destinations']} to see which destinations drive the most offerings and bookings.",
                }
            )

        while len(kpis) < 4:
            table = tables[len(kpis) % len(tables)]
            kpis.append(
                {
                    "number": len(kpis) + 1,
                    "name": f"{table['table'].replace('_', ' ').title()} Activity",
                    "description": f"Track row growth and recent activity in {table['full_name']} to monitor operational changes.",
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
    def _parse_kpi_suggestions(response: str) -> Optional[List[Dict]]:
        """
        Parse KPI suggestions from numbered list format.

        Expected format:
        1. KPI Name: Description
        2. KPI Name: Description
        ...
        """
        try:
            lines = response.split("\n")
            kpis = []

            for line in lines:
                line = line.strip()
                # Match numbered lines (1., 2., etc.)
                if line and line[0].isdigit() and "." in line:
                    # Extract number
                    number_str = line.split(".")[0].strip()
                    if not number_str.isdigit():
                        continue

                    number = int(number_str)

                    # Extract rest of line
                    rest = ".".join(line.split(".")[1:]).strip()

                    # Try to split on colon
                    if ":" in rest:
                        name, description = rest.split(":", 1)
                        name = name.strip()
                        description = description.strip()
                    else:
                        name = rest[:50]  # Take first 50 chars as name
                        description = rest

                    kpis.append(
                        {
                            "number": number,
                            "name": name,
                            "description": description,
                        }
                    )

            return kpis if kpis else None

        except Exception as e:
            logger.error(f"Error parsing KPI suggestions: {e}")
            return None

    @staticmethod
    def _extract_kpi_explanation(response: str) -> Optional[str]:
        """Extract explanation section from KPI response (after numbered list)."""
        try:
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
