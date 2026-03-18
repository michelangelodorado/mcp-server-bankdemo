FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.34.0" pydantic==2.10.4 websockets==14.1 sse-starlette==2.2.1 starlette
COPY server.py .
EXPOSE 8002
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002", "--log-level", "info"]
