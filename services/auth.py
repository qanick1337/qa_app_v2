import os
import secrets

from fastapi import Header, HTTPException

API_TOKEN = os.getenv("API_TOKEN")


def verify_token(x_api_key: str = Header(None)):
    if not API_TOKEN:
        raise HTTPException(status_code=500, detail="API_TOKEN is not configured on the server")

    if not x_api_key or not secrets.compare_digest(x_api_key, API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")