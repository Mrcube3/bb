FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY static ./static
COPY buyer_agent.py README.md DISCOVERY.md BINANCE_CAPABILITY_MATRIX.md ./
RUN pip install --no-cache-dir .
ENV PROMETHEUS_DB_PATH=/data/prometheus.db
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
