FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip

# Copy full project so package directories keep their names (including *_example clones)
COPY . /app/

# Install deps (includes Postgres extras to keep one image usable for both modes)
RUN pip install --no-cache-dir -e ".[postgres]"

EXPOSE 8000

CMD ["sh", "-lc", "uvicorn ${CLAB_APP_MODULE:-haiku_example.server:app} --host 0.0.0.0 --port 8000"]
