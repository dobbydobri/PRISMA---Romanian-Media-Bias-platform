FROM python:3.11-slim

# System dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    spacy \
    click \
    psycopg2-binary \
    networkx

RUN pip install --no-cache-dir cupy-cuda12x

RUN for i in 1 2 3; do \
        python -m spacy download ro_core_news_lg --timeout 300 && break \
        || echo "Attempt $i failed, retrying in 10s..." && sleep 10; \
    done

COPY . .

CMD ["python", "-u", "full_text_ner.py"]