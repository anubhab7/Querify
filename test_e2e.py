#!/usr/bin/env python3
"""Temporary end-to-end smoke test for the Querify API."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
BACKEND_ENV = ROOT / "backend" / ".env"
BASE_URL = os.getenv("QUERIFY_BASE_URL", "http://localhost:8000")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted = {}
        for key, value in payload.items():
            if "password" in key.lower() or "token" in key.lower():
                redacted[key] = "***"
            else:
                redacted[key] = redact_payload(value)
        return redacted
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


class HttpClient:
    def __init__(self) -> None:
        self._requests = None
        try:
            import requests  # type: ignore

            self._requests = requests
        except Exception:
            self._requests = None

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        url = f"{BASE_URL}{path}"
        headers = headers or {}

        if self._requests is not None:
            response = self._requests.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
                headers=headers,
                timeout=60,
            )
            try:
                body = response.json()
            except ValueError:
                body = response.text
            return response.status_code, body

        from urllib import error, parse, request

        if params:
            url = f"{url}?{parse.urlencode(params)}"

        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers = {"Content-Type": "application/json", **headers}

        req = request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=60) as response:
                raw_body = response.read().decode("utf-8")
                status_code = response.status
        except error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8")
            status_code = exc.code

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body
        return status_code, body


def print_response(label: str, status_code: int, body: Any) -> None:
    print(f"\n=== {label} ===")
    print(f"status: {status_code}")
    print(json.dumps(redact_payload(body), indent=2, default=str))


def expect_success(label: str, status_code: int, body: Any) -> None:
    if status_code >= 400:
        print_response(label, status_code, body)
        raise SystemExit(f"{label} failed with status {status_code}")


def extract_target_db_credentials() -> dict[str, Any]:
    env = load_env_file(BACKEND_ENV)
    target_url = env.get("DATABASE_URL")
    if not target_url:
        raise SystemExit("DATABASE_URL is missing from backend/.env")

    parsed = urlparse(target_url)
    if not all([parsed.hostname, parsed.path, parsed.username, parsed.password]):
        raise SystemExit("DATABASE_URL is not in a usable PostgreSQL URL format")

    ssl_value = parsed.query.lower()
    use_ssl = "sslmode=require" in ssl_value or parsed.port == 23011

    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "username": parsed.username,
        "password": parsed.password,
        "ssl": use_ssl,
    }


def first_table_name(schema_text: str) -> str:
    for line in schema_text.splitlines():
        stripped = line.strip()
        if stripped and ":" in stripped and "." in stripped:
            return stripped.split(":", 1)[0].split(".", 1)[1]
    raise SystemExit("Could not extract a table name from /schema response")


def main() -> None:
    client = HttpClient()
    suffix = int(time.time())
    credentials = extract_target_db_credentials()

    register_payload = {
        "email": f"qa{suffix}@gmail.com",
        "password": "QuerifyTest123",
    }
    status_code, body = client.request("POST", "/auth/register", json_body=register_payload)
    print_response("POST /auth/register", status_code, body)
    expect_success("POST /auth/register", status_code, body)

    token = body["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    status_code, body = client.request(
        "POST",
        "/auth/login",
        json_body=register_payload,
    )
    print_response("POST /auth/login", status_code, body)
    expect_success("POST /auth/login", status_code, body)

    status_code, body = client.request(
        "POST",
        "/database/connect",
        json_body=credentials,
    )
    print_response("POST /database/connect", status_code, body)
    expect_success("POST /database/connect", status_code, body)

    chat_payload = {
        **credentials,
        "title": f"E2E Chat {suffix}",
    }
    status_code, body = client.request(
        "POST",
        "/chats",
        json_body=chat_payload,
        headers=auth_headers,
    )
    print_response("POST /chats", status_code, body)
    expect_success("POST /chats", status_code, body)
    chat_id = body["session_id"]

    status_code, body = client.request(
        "POST",
        "/kpis",
        json_body={"session_id": chat_id},
        headers=auth_headers,
    )
    print_response("POST /kpis", status_code, body)
    expect_success("POST /kpis", status_code, body)
    if not isinstance(body.get("kpis"), list) or not body["kpis"]:
        raise SystemExit("POST /kpis did not return a populated KPI list")

    status_code, body = client.request(
        "GET",
        "/schema",
        params={"session_id": chat_id},
        headers=auth_headers,
    )
    print_response("GET /schema", status_code, body)
    expect_success("GET /schema", status_code, body)
    schema_text = body.get("schema", "")
    if not isinstance(schema_text, str) or not schema_text.strip():
        raise SystemExit("GET /schema did not return schema text")

    table_name = first_table_name(schema_text)
    query_payload = {
        "session_id": chat_id,
        "user_input": f"Show the first 5 rows from {table_name}",
        "preferred_model": "gemini",
    }
    status_code, body = client.request(
        "POST",
        "/query",
        json_body=query_payload,
        headers=auth_headers,
    )
    print_response("POST /query", status_code, body)
    expect_success("POST /query", status_code, body)
    if not body.get("sql_query") or not isinstance(body.get("results"), list):
        raise SystemExit("POST /query did not return SQL and result rows")

    status_code, body = client.request(
        "GET",
        f"/chats/{chat_id}/history",
        headers=auth_headers,
    )
    print_response("GET /chats/{chat_id}/history", status_code, body)
    expect_success("GET /chats/{chat_id}/history", status_code, body)

    messages = body.get("messages", [])
    if not messages:
        raise SystemExit("History endpoint returned no messages")
    latest_message = messages[-1]
    if not isinstance(latest_message.get("results"), list):
        raise SystemExit("History endpoint did not include results as an array")

    print("\nE2E flow passed successfully.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
