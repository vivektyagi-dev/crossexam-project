# macOS / Linux shortcuts (Windows users: scripts\*.cmd do the same). Needs Docker Desktop.
#   make setup      create .env from the template (then put your Gemini key in it)
#   make up         build and start everything (web 8080, API 8000, Flower 5555)
#   make demo-data  generate demo papers + matching master data   (N=10 shipments by default)
#   make test       run the 25 tests with the scripted model: no key, no cost
#   make eval       score the latest batch against the generator's ground truth
#   make down       stop;  make reset  stop and delete all data
N ?= 10

.PHONY: setup up monitoring demo-data test eval down reset logs
setup:
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "Created .env: set GOOGLE_API_KEY in it")

up:
	docker compose up --build -d
	@echo "Web http://localhost:8080   API http://localhost:8000/docs   Flower http://localhost:5555"

monitoring:
	docker compose --profile monitoring up --build -d
	@echo "Grafana http://localhost:3000"

demo-data:
	docker compose run --rm -v "$(CURDIR)/data:/app/data" api python -m datagen.generate --shipments $(N) --ensure-each-problem --out /app/data/generated
	docker compose run --rm -v "$(CURDIR)/data:/app/data" api python -m app.db.seed /app/data/generated/master.json
	@echo "Now upload the files in data/generated/files from the web screen"

test:
	docker compose up -d postgres redis
	docker compose run --rm --no-deps -v "$(CURDIR)/tests:/app/tests" -v "$(CURDIR)/pyproject.toml:/app/pyproject.toml" \
	  -e TEST_DATABASE_URL=postgresql+psycopg://crossexam:crossexam@postgres:5432/crossexam_test \
	  -e REDIS_URL=redis://redis:6379/15 -e TEST_DATA_DIR=/app/data/test_generated api \
	  sh -c "pip install -q pytest==9.1.1 fakeredis==2.40.0 ruff==0.17.1 >/dev/null 2>&1; python -m ruff check --no-cache . && python -m pytest -q -p no:cacheprovider"

eval:
	docker compose run --rm --no-deps -v "$(CURDIR)/data:/app/data" api python -m eval.run_eval --truth /app/data/generated/ground_truth.json --out /app/data/eval_report.md

logs:
	docker compose logs -f --tail=50 worker-agent worker-reader

down:
	docker compose down

reset:
	docker compose down -v
