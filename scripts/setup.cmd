@echo off
REM One-time setup: create .env from the template.
if not exist .env (
  copy .env.example .env
  echo Created .env - open it and set GOOGLE_API_KEY before starting.
) else (
  echo .env already exists.
)
