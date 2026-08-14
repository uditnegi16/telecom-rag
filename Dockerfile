FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding + reranker weights into the image.
# Downloading them at container start adds ~90s to cold boot and makes the
# container depend on Hugging Face being reachable at runtime - a needless
# availability dependency for a demo that must work on first click.
ENV HF_HOME=/opt/hf
RUN python -c "\
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY . .

ENV PYTHONUNBUFFERED=1 \
    DEMO_QUESTION_LIMIT=8 \
    DEMO_GLOBAL_DAILY_CAP=300 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "ui/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]
