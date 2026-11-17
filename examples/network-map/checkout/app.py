from fastapi import FastAPI
import httpx

app = FastAPI()

@app.get("/checkout")
def checkout():
    httpx.get("https://shared.example.com:443/inventory")
    httpx.post("https://shared.example.com:8443/payments")
    httpx.post("https://events.example.com/orders")
