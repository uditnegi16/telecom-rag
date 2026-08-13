FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Model weights are downloaded at runtime into a mounted volume rather than
# baked into the image - see DECISION_LOG D-014. Baking them adds ~2GB.
ENV HF_HOME=/app/data/hf_cache

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
