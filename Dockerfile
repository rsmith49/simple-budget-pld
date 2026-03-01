FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────────────
# build-essential is needed for compiling any C-extension packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
COPY cloud_requirements.txt .
RUN pip install --no-cache-dir -r cloud_requirements.txt

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

# ── Streamlit configuration ────────────────────────────────────────────────────
# These are read by Streamlit at startup. Setting them here avoids needing
# a streamlit/config.toml file inside the container.
ENV STREAMLIT_SERVER_PORT=8080
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_ENABLE_CORS=false
# Raise the default max upload limit in case large CSVs are ever uploaded.
ENV STREAMLIT_SERVER_MAX_UPLOAD_SIZE=200

# ── Runtime ────────────────────────────────────────────────────────────────────
EXPOSE 8080

CMD ["streamlit", "run", "scripts/st_dashboard.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
