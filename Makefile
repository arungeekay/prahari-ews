.PHONY: demo data train frontend serve docker

demo:  ## one command: install, build frontend, generate data, train, serve
	pip install -r requirements.txt
	cd frontend && npm install && npm run build
	python scripts/train_all.py --seed 42 --data data
	DATA_DIR=data MODEL_DIR=data/models FRONTEND_DIR=frontend/dist uvicorn backend.app:app --host 0.0.0.0 --port 8001

docker:
	docker build -t prahari-ews . && docker run -p 8001:8001 prahari-ews
