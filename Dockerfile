# Sprint Copilot — container image
# Build:  docker build -t sprint-copilot .
# Run:    docker run -p 8501:8501 -e ANTHROPIC_API_KEY=sk-ant-... sprint-copilot

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

# Dependencies first so code edits don't bust the layer cache.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the demo dataset into the image so the first request is instant.
RUN python data/generate_data.py

# Run unprivileged; the app writes to data/ when regenerating the demo set.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status == 200 else 1)"

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.runOnSave=false", \
     "--browser.gatherUsageStats=false"]
