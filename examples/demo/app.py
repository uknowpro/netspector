import os
import httpx
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/weather")
def weather():
    return httpx.get("https://weather.example.com/v1/current").json()


def notify():
    return httpx.post(os.getenv("NOTIFY_URL"))
