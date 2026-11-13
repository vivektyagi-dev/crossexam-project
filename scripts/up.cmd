@echo off
REM Start the full local stack (add "monitoring" as an argument for Prometheus + Grafana).
if "%1"=="monitoring" (
  docker compose --profile monitoring up --build -d
) else (
  docker compose up --build -d
)
echo.
echo   Web screen   http://localhost:8080
echo   API docs     http://localhost:8000/docs
echo   Flower       http://localhost:5555
if "%1"=="monitoring" echo   Grafana      http://localhost:3000
