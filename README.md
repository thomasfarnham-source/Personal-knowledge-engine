Personal Knowledge Engine
A FastAPI backend and Typer‑based CLI for a personal knowledge system that parses, ingests, stores, and searches notes for long‑term retrieval and analysis.
This project provides:
- A FastAPI backend for querying and retrieval
- A Supabase‑backed storage layer for notes, embeddings, and metadata
- A clean, two‑stage ingestion pipeline (pke parse → pke ingest)
- Pluggable parsers for local exports (e.g., Joplin Markdown)
- A contributor‑friendly CLI built with Typer
- Environment‑driven configuration so secrets remain local and safe

🚀 Quickstart
1. Clone and set up the environment
git clone https://github.com/<your-org>/Personal-knowledge-engine.git
cd Personal-knowledge-engine

python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt



2. Configure environment variables
Copy the example file:
cp .env.example .env


Edit .env and add:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
These values stay local only. .env is intentionally ignored by Git.
Example:
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key



🧩 Two‑Stage Ingestion Pipeline
The CLI provides a clean, explicit ingestion workflow.

Stage 1 — Parse Joplin Markdown exports
pke parse run \
  --export-path path/to/joplin_export \
  --output pke/artifacts/parsed/parsed_notes.json


This produces a structured JSON artifact containing all parsed notes.
Default output location:
pke/artifacts/parsed/parsed_notes.json


This file is the input to Stage 2.

Stage 2 — Ingest parsed notes into Supabase
pke ingest run \
  --parsed-path pke/artifacts/parsed/parsed_notes.json \
  --dry-run


Use --dry-run to validate ingestion without writing to Supabase.
You can also limit ingestion for testing:
pke ingest run --limit 10



🧠 Running the FastAPI Backend
Once ingestion is complete, start the API:
uvicorn main:app --reload --host 0.0.0.0 --port 8000


Open:
http://localhost:8000/docs


to explore the API.

🗂 Project Structure
pke/
  cli/                 # Typer-based CLI (parse, ingest, notes)
  ingestion/           # Orchestrator + Supabase integration
  parsers/             # Joplin Markdown parser and future parsers
  artifacts/           # Generated pipeline artifacts (gitignored)
  tests/               # Test suite
  main.py              # FastAPI entrypoint



🔐 Environment Variables
Keep real secrets out of the repo. Only .env.example is tracked.
Required:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
Optional variables can be added as the system grows.

🚀 Deployment
- Backend hosting: Render, Fly.io, Heroku, Azure, AWS, or any container platform
- CI/CD: GitHub Actions recommended for tests + deploy on push to main
- Secrets: Store in GitHub Secrets or platform‑specific config vars
- Frontend (optional): Vercel or Netlify pair well with FastAPI backends

🤝 Contributing
- Fork the repo and create a feature branch
- Add tests for new behavior
- Keep local‑only config (e.g., .env, config.py) out of Git
- Follow existing patterns for CLI structure and ingestion logic

📄 License
Add your preferred license (e.g., MIT, Apache 2.0) and update this section.


