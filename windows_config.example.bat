@echo off
REM Copy this file to windows_config.bat and fill in your own values.
REM windows_config.bat is ignored by Git and must never be uploaded.

set MACD_RUNTIME_MODE=windows

REM Optional: central PostgreSQL shared by Windows and cloud.
REM Use the EXTERNAL connection URL on Windows.
REM Example format only:
REM set SHARED_DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require

REM Optional: choose another local cache/data directory.
REM set MACD_DATA_DIR=D:\MACD-DATA

REM Optional: screenshot holding import API key.
REM set DEEPSEEK_API_KEY=

REM Preferred market-data source: Tonghuashun iFinD HTTP API.
REM Paste your Refresh Token here ONLY in local windows_config.bat.
REM Never commit the real token to GitHub.
REM set IFIND_REFRESH_TOKEN=
