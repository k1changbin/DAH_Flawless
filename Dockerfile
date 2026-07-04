FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY README.md pyproject.toml streamlit_app.py ./
COPY src ./src
COPY tests ./tests

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "dah_flawless.main", "--seed", "42", "--rounds", "5", "--out", "data/logs/round_logs.jsonl", "--summary", "data/logs/summary.json"]
