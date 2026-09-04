# Multi-stage: build the React frontend, then serve the static bundle from FastAPI.
# The seed-42 data and trained models are BAKED at build time (deterministic), so the container
# answers /api/health within seconds instead of retraining for minutes on every cold start.
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data MODEL_DIR=/app/data/models \
    FRONTEND_DIR=/app/frontend/dist PORT=8001 DATA_SOURCE=synthetic
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core/ ./core/
COPY backend/ ./backend/
COPY mock/ ./mock/
COPY scripts/ ./scripts/
COPY data/ ./data/
# artefacts shipped in the repo (seed 42, trained on the reference machine) are used as-is; train only if absent
RUN [ -f /app/data/models/pd_model.pkl ] || python scripts/train_all.py --seed 42 --data /app/data
COPY --from=frontend /fe/dist ./frontend/dist
COPY start.sh .
RUN chmod +x start.sh
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=10 \
  CMD python -c "import urllib.request,sys,json,os; d=json.load(urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8001')+'/api/health')); sys.exit(0 if d.get('status')=='ok' else 1)"
CMD ["./start.sh"]
