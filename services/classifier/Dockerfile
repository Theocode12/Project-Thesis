FROM python:3.13-slim

WORKDIR /app

COPY services/classifier/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared/ shared/
COPY services/classifier/ .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
