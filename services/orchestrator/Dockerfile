FROM python:3.13-slim

WORKDIR /app

COPY services/orchestrator/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared/ shared/
COPY services/orchestrator/ .

CMD ["python", "app.py"]
