@echo off
REM Generate demo documents and load the matching master data (POs, GRNs, suppliers).
REM Usage: scripts\demo-data.cmd [shipments]   (default 60; ~5 files per shipment)
set N=%1
if "%N%"=="" set N=60
docker compose run --rm -v "%cd%\data:/app/data" api python -m datagen.generate --shipments %N% --ensure-each-problem --out /app/data/generated
docker compose run --rm -v "%cd%\data:/app/data" api python -m app.db.seed /app/data/generated/master.json
echo.
echo Upload the files in data\generated\files from the web screen.
