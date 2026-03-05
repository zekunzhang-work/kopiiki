# ─────────────────────────────────────────────────
#  Kopiiki — Multi-stage Dockerfile
#  Produces a single container serving both the
#  React frontend and Flask+Playwright backend.
# ─────────────────────────────────────────────────

# ── Stage 1: Build the React frontend ────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Runtime (Python + Playwright) ───────
FROM python:3.11-slim
WORKDIR /app

# Install system deps required by Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libx11-xcb1 \
    fonts-liberation wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

# Copy backend source
COPY backend/ ./

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./static

# Environment: tell Flask to serve the frontend
ENV KOPIIKI_STATIC_DIR=/app/static
ENV PORT=5000

EXPOSE 5000

CMD ["python", "app.py"]
