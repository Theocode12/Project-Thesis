FROM python:3.13-slim

WORKDIR /app

COPY services/sensor-generator/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/shared/ shared/
COPY services/sensor-generator/ .

CMD ["python", "app.py"]
