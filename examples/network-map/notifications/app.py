from fastapi import FastAPI
import httpx

app = FastAPI()

@app.post("/notify")
def notify():
    httpx.post("https://shared.example.com/messages")
    httpx.post("https://shared.example.com/messages")
