@echo off
REM Unit + end-to-end tests (scripted fake model, no API key, no cost).
docker compose up -d postgres redis
set TEST_DATABASE_URL=postgresql+psycopg://crossexam:crossexam@localhost:5432/crossexam_test
python -m pytest -q
