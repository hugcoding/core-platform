FROM python:3.13-alpine
WORKDIR /app
RUN pip install --no-cache-dir psycopg2-binary==2.9.10 redis==6.2.0
COPY core ./core
COPY workset_ai_worker.py ./workset_ai_worker.py
COPY project/prompts/scrum-101-workset-llm-v2.json ./project/prompts/scrum-101-workset-llm-v2.json
COPY tests/integration/workset-ai-fallback/run.py ./run.py
CMD ["python", "run.py"]
