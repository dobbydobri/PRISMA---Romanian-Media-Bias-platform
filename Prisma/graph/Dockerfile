FROM python:3.11-slim

# System dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    psycopg2-binary \
    networkx \
    roner \
    stanza

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu121 \
    torch==2.3.0

RUN python -c "\
import stanza; \
stanza.download('ro', processors='tokenize,lemma', verbose=False); \
import roner; \
_ = roner.NER(use_gpu=False, batch_size=1, named_persons_only=True); \
print('RoNER and Stanza models downloaded successfully')"

COPY . .

CMD ["python", "-u", "full_text_ner.py"]