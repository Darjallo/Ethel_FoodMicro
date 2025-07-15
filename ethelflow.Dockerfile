FROM python:3.12-slim

WORKDIR /app

COPY ethelflow ethelflow
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["python", "-m", "ethelflow"]