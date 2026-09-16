FROM nas-dashboard:latest
RUN pip install --no-cache-dir httpx==0.28.1
COPY core ./core
COPY dashboard ./dashboard
COPY database ./database
COPY tests ./tests
COPY finance_worker.py workset_ai_worker.py controlled_execution_worker.py workset_ocr_worker.py ./
