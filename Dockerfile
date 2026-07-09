FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt

COPY configs ./configs
COPY scripts ./scripts
COPY src ./src
COPY tests ./tests
COPY docs ./docs
COPY streamlit_app.py ./

# Pre-built React dashboard (single-file bundle, served as static asset — no Node needed at runtime).
COPY frontend/dist ./frontend/dist

RUN mkdir -p data/logs data/frontend data/reports tmp/world

EXPOSE 8080 8501

CMD ["python", "-m", "dah_flawless.main", "--seed", "42", "--rounds", "5", "--out", "data/logs/round_logs.jsonl", "--summary", "data/logs/summary.json"]
