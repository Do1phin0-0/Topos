FROM python:3.11-slim

WORKDIR /app

COPY titan/requirements.txt titan/requirements.txt
RUN pip install --no-cache-dir -r titan/requirements.txt

COPY titan/ titan/

ENV PYTHONPATH=/app

CMD ["uvicorn", "titan.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
