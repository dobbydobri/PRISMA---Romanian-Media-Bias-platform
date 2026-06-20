FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask app
COPY query_server.py .

EXPOSE 8081

CMD ["gunicorn", \
     "-w", "1", \
     "-k", "sync", \
     "-b", "0.0.0.0:8081", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "query_server:app"]