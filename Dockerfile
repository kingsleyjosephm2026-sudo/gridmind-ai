FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
ENV VITE_API_URL=""
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gridmind ./gridmind
COPY api ./api
COPY --from=ui /ui/dist ./static
ENV GRIDMIND_DB=/tmp/gridmind.db
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
