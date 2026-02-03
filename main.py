#!/usr/bin/env python3
"""Real-Time News Bot - Combined single file version"""
import asyncio
import aiohttp
import os
from datetime import datetime, timedelta

# Configuration from environment
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "SPY", "QQQ"]
seen_news = set()

async def fetch_news(session, symbol):
    today = datetime.now()
    from_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={from_date}&to={today.strftime('%Y-%m-%d')}&token={FINNHUB_API_KEY}"
    async with session.get(url) as resp:
        return await resp.json() if resp.status == 200 else []

async def send_telegram(session, channel, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    await session.post(url, json={"chat_id": channel, "text": text, "parse_mode": "HTML"})

async def main():
    print("Starting Real-Time News Bot...")
    async with aiohttp.ClientSession() as session:
        while True:
            for symbol in DEFAULT_WATCHLIST:
                news = await fetch_news(session, symbol)
                for item in news[:3]:
                    news_id = f"{item.get('headline','')}_{item.get('datetime','')}"
                    if news_id not in seen_news:
                        seen_news.add(news_id)
                        msg = f"<b>${symbol}</b>\\n{item.get('headline','')}"
                        if TELEGRAM_TAPE_CHANNEL:
                            await send_telegram(session, TELEGRAM_TAPE_CHANNEL, msg)
                            print(f"Posted: {symbol} - {item.get('headline','')[:50]}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
