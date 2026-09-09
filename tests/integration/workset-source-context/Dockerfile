FROM python:3.13-alpine
WORKDIR /app
RUN pip install --no-cache-dir psycopg2-binary==2.9.10
COPY database/migrations/20260908_add_workset_source_context.sql ./database/migrations/20260908_add_workset_source_context.sql
COPY tests/integration/workset-source-context/run.py ./run.py
CMD ["python", "run.py"]
