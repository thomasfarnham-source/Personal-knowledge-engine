from fastapi import FastAPI

from supabase_client import supabase

app = FastAPI()


@app.get("/")
def read_root() -> dict:
    return {"message": "Hello, FastAPI is live!"}


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/db-test")
async def db_test() -> dict:
    if supabase is None:
        return {"status": "error", "message": "Supabase client not initialized"}
    try:
        response = supabase.table("documents").select("*").limit(1).execute()
        return {"status": "success", "data": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
