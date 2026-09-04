FROM python:3.13-alpine
WORKDIR /app
RUN pip install --no-cache-dir psycopg2-binary==2.9.10 redis==6.2.0
COPY core ./core
COPY controlled_execution_worker.py ./controlled_execution_worker.py
COPY database/migrations/20260829_add_controlled_execution_queue.sql ./database/migrations/20260829_add_controlled_execution_queue.sql
COPY database/migrations/20260830_enhance_controlled_execution_progress.sql ./database/migrations/20260830_enhance_controlled_execution_progress.sql
COPY tests/integration/controlled-execution/run.py ./run.py
COPY database/migrations/20260904_execution_event_order.sql ./database/migrations/20260904_execution_event_order.sql
CMD ["python", "run.py"]
