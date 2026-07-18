FROM python:3.13-slim

WORKDIR /app

COPY services/data-management/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared/ shared/
COPY services/data-management/ .

CMD ["python", "app.py"]
