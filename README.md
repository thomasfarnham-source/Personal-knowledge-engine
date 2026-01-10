Personal-knowledge-engine
FastAPI backend for a personal knowledge system that ingests, parses, and stores notes for search and analysis.

<!-- Trigger CI test -->

Features
- FastAPI backend with async endpoints for ingestion and querying.
- Supabase integration for persistent storage and search.
- Pluggable ingestion scripts for parsing notes and syncing from local exports.
- Environment-driven configuration so secrets remain local and safe.
- Tests and utilities under tests/ and scripts/.

Quickstart
Clone and prepare the environment
git clone https://github.com/<your-org>/Personal-knowledge-engine.git
cd Personal-knowledge-engine
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS or Linux
source .venv/bin/activate
pip install -r requirements.txt


Create local environment file
# Copy the example and edit values
cp .env.example .env
# Edit .env to add your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY


Run the app
uvicorn main:app --reload --host 0.0.0.0 --port 8000


Open http://localhost:8000/docs to explore the API.

Environment variables
Keep real secrets out of the repo. Use .env for local secrets and keep .env in .gitignore. Track .env.example with placeholders only.
Required variables
- SUPABASE_URL — your Supabase project URL.
- SUPABASE_SERVICE_ROLE_KEY — service role key for server-side access.
Example .env.example
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key



Deployment
- Backend hosting: Deploy the FastAPI app to platforms such as Render, Fly, Heroku, or an Azure/AWS VM or container.
- CI/CD: Use GitHub Actions to run tests and deploy on push to main. Store secrets in the platform’s secret store (GitHub Secrets, Render/Heroku config vars, etc.).
- Frontend: If you add a frontend, consider Vercel or Netlify for static hosting.

Contributing
- Workflow: Fork the repo, create a feature branch, open a PR with a clear description and tests for new behavior.
- Local config: Add local-only config files (for example config.py or .env) to .gitignore.
- Code style: Follow existing project patterns and add tests for new functionality.

License
Add your preferred license file (for example LICENSE) to the repository and update this section accordingly.

I can create a ready-to-run GitHub Actions workflow for CI/CD or a PowerShell script to automate setup — reply create workflow or create script to get one

