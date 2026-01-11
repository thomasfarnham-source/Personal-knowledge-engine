from fastapi import FastAPI
from supabase_client import supabase  # Import Supabase client

app = FastAPI()


@app.get("/")
def read_root() -> None:
    return {"message": "Hello, FastAPI is live!"}


@app.get("/health")
def health_check() -> None:
    return {"status": "ok"}


# Route to test Supabase connectivity
@app.get("/db-test")
async def db_test() -> None:
    try:
        # Attempt to fetch one row from the 'documents' table
        response = supabase.table("documents").select("*").limit(1).execute()
        return {"status": "success", "data": response.data}
    except Exception as e:
        # Return the error message if something goes wrong
        return {"status": "error", "message": str(e)}
