FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The build context is the repository root so the package and shared runtime
# files retain the same paths used by local development.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY data_agent ./data_agent
COPY alembic.ini ./
COPY migrations ./migrations
COPY langgraph.json ./

EXPOSE 8000 2024

CMD ["uvicorn", "data_agent.agent_server:app", "--host", "0.0.0.0", "--port", "8000"]
