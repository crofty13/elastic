FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY event_generator.py .
COPY Elastic_indexes ./Elastic_indexes

ENV PYTHONUNBUFFERED=1
ENV ELASTIC_INDEXES_DIR=/app/Elastic_indexes

EXPOSE 5005

CMD ["python", "event_generator.py"]
