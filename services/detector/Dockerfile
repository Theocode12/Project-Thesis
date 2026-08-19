FROM python:3.13-slim

WORKDIR /app

COPY services/detector/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared/ shared/
COPY services/detector/ .

CMD ["python", "app.py"]
