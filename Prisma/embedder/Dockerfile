FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install spacy click
RUN pip install spacy psycopg2-binary
RUN PIP_DEFAULT_TIMEOUT=1000 python -m spacy download ro_core_news_lg

COPY . .

CMD ["python", "-u", "main.py"]