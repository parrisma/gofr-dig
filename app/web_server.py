#!/usr/bin/env python3
\"\"\"Web server placeholder - minimal FastAPI server.\"\"\"

from fastapi import FastAPI
from app.logger import session_logger as logger

app = FastAPI(title=\"gofr-dig-web\")

@app.get(\"/health\")
async def health():
    return {\"status\": \"ok\"}

@app.get(\"/\")
async def root():
    return {\"service\": \"gofr-dig\", \"status\": \"running\"}
