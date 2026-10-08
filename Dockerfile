FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[production]" \
    && useradd --create-home --uid 10001 leads

USER leads

EXPOSE 8765

CMD ["leads-workstation", "serve", "--host", "0.0.0.0", "--port", "8765", "--allow-network"]
