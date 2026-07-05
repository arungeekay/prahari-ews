# Multi-stage: build the React frontend, then serve the static bundle from FastAPI.
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data MODEL_DIR=/app/data/models \
    FRONTEND_DIR=/app/frontend/dist PORT=8001
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core/ ./core/
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY --from=frontend /fe/dist ./frontend/dist
COPY start.sh .
RUN chmod +x start.sh
EXPOSE 8001
CMD ["./start.sh"]
