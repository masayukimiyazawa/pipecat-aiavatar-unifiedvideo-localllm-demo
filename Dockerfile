FROM python:3.13-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml

COPY . .

EXPOSE 8005

CMD ["uv", "run", "python", "server.py"]
