from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import API_AUTH_ENABLED, API_KEY


def require_api_key(x_api_key: Annotated[str | None, Header(alias='X-API-Key')] = None) -> None:
    if not API_AUTH_ENABLED:
        return
    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={'code': 'api_key_not_configured', 'message': 'API authentication is enabled but API_KEY is not configured'},
        )
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={'code': 'unauthorized', 'message': 'A valid API key is required'},
        )
