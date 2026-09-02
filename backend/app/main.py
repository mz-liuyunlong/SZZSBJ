from fastapi import FastAPI

app = FastAPI(title="YC System API")


@app.get("/health")
def health_check() -> dict[str, object]:
    return {
        "success": True,
        "data": {"status": "ok"},
        "error": None,
        "meta": None,
    }
