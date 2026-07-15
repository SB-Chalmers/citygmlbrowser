# CityGML Browser (In Progress)

This repository now includes a lightweight browser stack for CityGML files:

- Python API: parses uploaded CityGML and returns graph payloads.
- React app: uploads any .gml file and lets you browse graph nodes and properties.

## Current Support

- CityGML: 2.0
- Energy ADE: 2.0

The API detects unsupported dialects and returns structured errors for now.

## Project Structure

- parse.py: existing CityGML parser logic (reused)
- app.py: existing graph builder logic (reused)
- api/server.py: FastAPI upload endpoints and logging
- api/dialect.py: namespace-based dialect detection
- web/: React + TypeScript + Tailwind browser UI

## Run Backend API

1. Create and activate a Python environment.
2. Install dependencies:

   pip install -r requirements-api.txt

3. Start server:

   uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

4. Health check:

   GET http://localhost:8000/api/v1/health

## Quick Start (Single Command)

From the repository root:

1. Install launcher dependencies once:

   npm install

2. Install frontend dependencies once:

   npm run setup

3. Start backend and frontend together:

   npm run dev

This starts:

- Backend API on http://localhost:8000
- Frontend app on http://localhost:5173

## Run Frontend

1. Go to frontend folder:

   cd web

2. Install dependencies:

   npm install

3. Set API base URL (optional, defaults to http://localhost:8000):

   cp .env.example .env

4. Start frontend:

   npm run dev

## API Endpoints

- POST /api/v1/graph-file
  - multipart/form-data with file field
  - returns graph nodes, edges, typeColors, and dialect info

- POST /api/v1/parse-file
  - multipart/form-data with file field
  - returns parsed model plus summary counts

## Notes on Scope

This is intentionally not overengineered.

- One API service.
- One frontend app.
- One extension seam: dialect detection + support checks.

Future support for CityGML 3.0 and Energy ADE 3.0 can be added without changing the frontend contract.
