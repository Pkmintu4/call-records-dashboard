FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json /app/frontend/
RUN npm ci

COPY frontend /app/frontend

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY backend /app/backend
RUN pip install --no-cache-dir -e .

# Bundle the built frontend into the backend image for single-service cloud deploys.
COPY --from=frontend-build /app/frontend/dist /app/backend/app/static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
