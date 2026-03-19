"""
LLM Service for orchestrating Gemini and Perplexity API calls.
Handles message normalization, fallback logic, and context-aware query generation.
"""

import os
import logging
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

        # Try preferred model first
        model_used = preferred_model
        result = await self._call_llm(preferred_model, messages)

        if result is None or result.strip() == "":
            # Fallback to other model
            fallback_model = "perplexity" if preferred_model == "gemini" else "gemini"
            logger.warning(
                f"Preferred model {preferred_model} failed, attempting fallback {fallback_model}"
            )
            model_used = fallback_model
            result = await self._call_llm(fallback_model, messages)

        if result is None or result.strip() == "":
            logger.error("Both LLM models failed to generate response")
            return None, None, model_used

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

        # Try preferred model first
        model_used = preferred_model
        result = await self._call_llm(preferred_model, messages)

        if result is None or result.strip() == "":
            fallback_model = "perplexity" if preferred_model == "gemini" else "gemini"
            logger.warning(
                f"Preferred model {preferred_model} failed, attempting fallback {fallback_model}"
            )
            model_used = fallback_model
            result = await self._call_llm(fallback_model, messages)

        if result is None or result.strip() == "":
            logger.error("Both LLM models failed to generate KPI suggestions")
            return None, None, model_used

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
            # Convert messages to Gemini format
            chat_history = []
            system_instruction = None

            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                else:
                    chat_history.append(
                        {
                            "role": "model" if msg["role"] == "assistant" else "user",
                            "parts": [msg["content"]],
                        }
                    )

            # Use generative model
            model = genai.GenerativeModel(
                self.gemini_model,
                system_instruction=system_instruction,
            )

            response = model.generate_content(
                chat_history[-1]["parts"][0] if chat_history else "",
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
