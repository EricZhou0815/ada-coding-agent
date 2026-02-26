FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY agents/ agents/
COPY tools/ tools/
COPY orchestrator/ orchestrator/

COPY docker/entrypoint.py /app/entrypoint.py
ENTRYPOINT ["python3", "/app/entrypoint.py"]