@echo off
REM Score the latest batch against the generator's ground truth.
docker compose run --rm -v "%cd%\data:/app/data" api python -m eval.run_eval --truth /app/data/generated/ground_truth.json --out /app/data/eval_report.md
