@echo off
REM Local stand-in for the month-end scale-up: scripts\scale-workers.cmd 3
set N=%1
if "%N%"=="" set N=2
docker compose up -d --scale worker-reader=%N% --scale worker-agent=%N% --no-recreate
