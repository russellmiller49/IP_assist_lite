#!/usr/bin/env python3
"""
Main entry point for IP Assist Lite API
Imports the FastAPI app from fastapi_app.py
"""

from fastapi_app import app

# This allows uvicorn to import the app as "main:app"
__all__ = ["app"]
