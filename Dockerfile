# Python 3.11 is REQUIRED: the backend ships as sourceless *.pyc bytecode, which
# only imports on the exact interpreter version it was compiled for (3.11).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# serve.py binds 0.0.0.0 and honors $PORT (Render/most PaaS inject it).
ENV HOST=0.0.0.0
EXPOSE 8000
CMD ["python", "serve.py"]
