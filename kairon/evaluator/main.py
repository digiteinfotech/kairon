from fastapi import FastAPI

from kairon.api.models import Response

from kairon.evaluator.router import pyscript

app = FastAPI()


@app.get("/", response_model=Response)
def index():
    return {"message": "Running Evaluator"}


app.include_router(pyscript.router, tags=["Evaluator"])

