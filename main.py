import hmac
import json
import logging
import os
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level="INFO", format="%(asctime)s | %(message)s")
log = logging.getLogger("assistant")

BOT_TOKEN = "9065532774:AAEJuItSw8u6hF2YRI68aGnEV0ZU83-2KV8"
SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None

app = FastAPI(title="NQ Assistant", docs_url=None, redoc_url=None)


def _check_key(key: str) -> None:
    if not SECRET or not hmac.compare_digest(key.encode(), SECRET.encode()):
        raise HTTPException(status_code=401, detail="Wrong key")


async def _find_chat_id(client: httpx.AsyncClient) -> Optional[str]:
    global _chat_id
    if _chat_id:
        return _chat_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    data = (await client.get(url)).json()
    for update in reversed(data.get("result", [])):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            _chat_id = str(chat["id"])
            log.info("Telegram chat found")
            return _chat_id
    return None


async def send_telegram(text: str) -> str:
    if not BOT_TOKEN:
        return "TELEGRAM_BOT_TOKEN is missing in Render settings"
    async with httpx.AsyncClient(timeout=10) as client:
        chat_id = await _find_chat_id(client)
        if not chat_id:
            return ("Bot can't find you yet. Open your bot in Telegram, "
                    "press Start, send it the word hi, then try again")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = await client.post(url, json={"chat_id": chat_id,
                                            "text": text[:4000]})
        if resp.status_code != 200:
            log.warning("Telegram error: %s", resp.text[:200])
            return f"Telegram refused the message: {resp.text[:150]}"
    return "ok"


@app.get("/")
@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/test")
async def test(key: str = "") -> dict:
    _check_key(key)
    result = await send_telegram("Test: your NQ assistant is connected.")
    return {"result": result}


@app.post("/alert")
async def alert(request: Request, key: str = "") -> dict:
    _check_key(key)
    raw = (await request.body()).decode("utf-8", errors="replace").strip()
    text = raw
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "message" in parsed:
            text = str(parsed["message"])
    except ValueError:
        pass
    result = await send_telegram(f"TradingView alert:\n{text or '(empty)'}")
    log.info("Alert handled: %s", result)
    return {"result": result}
