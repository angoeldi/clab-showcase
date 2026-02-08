FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip

# Copy project first so editable install works
COPY pyproject.toml README.md /app/
COPY clab_bot /app/clab_bot
COPY configs /app/configs

# Install deps (includes Postgres extras to keep one image usable for both modes)
RUN pip install --no-cache-dir -e ".[postgres]"

EXPOSE 8000

CMD ["uvicorn", "clab_bot.server:app", "--host", "0.0.0.0", "--port", "8000"]
