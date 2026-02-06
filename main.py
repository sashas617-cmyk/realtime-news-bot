#!/usr/bin/env python3
"""Real-Time News Bot with Massive.com API (Benzinga) - v4"""
import asyncio, aiohttp, os, json, re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import RetryAfter

BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_WATCHLIST = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")
MESSAGE_DELAY = 2.0
DATA_FILE = "/tmp/newsbot_data.json"
seen_news = set()
MASSIVE_API_URL = "https://api.massive.com/benzinga/v2/news"

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f: return json.load(f)
    except: pass
    return {"watchlist": INITIAL_WATCHLIST.split(","), "keywords": [k.strip().lower() for k in INITIAL_KEYWORDS.split(",") if k.strip()]}

async def fetch_news(session, tickers=None, limit=50):
    params = {'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}
    if tickers: params['tickers'] = ','.join(tickers)
    try:
        async with session.get(MASSIVE_API_URL, params=params, headers={'Accept': 'application/json'}) as r:
            return (await r.json()).get('results', []) if r.status == 200 else []
    except: return []

async def fetch_keyword_news(session, keywords, limit=100):
    if not keywords: return []
    try:
        async with session.get(MASSIVE_API_URL, params={'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}, headers={'Accept': 'application/json'}) as r:
            if r.status != 200: return []
            return [a for a in (await r.json()).get('results', []) if any(kw in (a.get('title','')+'|'+a.get('teaser','')).lower() for kw in keywords)]
    except: return []

def fmt(a):
    t = a.get('title',''); ts = a.get('teaser',''); au = a.get('author',''); url = a.get('url','')
    st = a.get('stocks',[]); tk = ', '.join([s.get('name','') if isinstance(s,dict) else s for s in st[:5]]) if st else ''
    m = f"<b>{t}</b>"; m += f"\n<i>Tickers: {tk}</i>" if tk else ""; m += f"\n\n{ts[:300]}" if ts else ""; m += f"\n<i>By {au}</i>" if au else ""; m += f'\n<a href="{url}">Read more</a>' if url else ""
    return m

async def send(bot, cid, txt):
    for _ in range(3):
        try: await bot.send_message(chat_id=cid, text=txt, parse_mode='HTML', disable_web_page_preview=True); return True
        except RetryAfter as e: await asyncio.sleep(e.retry_after+1)
        except Exception as e:
            if "flood" in str(e).lower(): await asyncio.sleep(30)
            else: return False
    return False

async def loop(app):
    global seen_news; bot = app.bot; d = load_data(); wl = d.get("watchlist",[]); kw = d.get("keywords",[])
    print(f"Start: tickers={wl}, keywords={kw}")
    async with aiohttp.ClientSession() as s:
        for a in (await fetch_news(s,wl,30)) + (await fetch_keyword_news(s,kw,50)):
            nid = a.get('benzinga_id') or a.get('id')
            if nid and nid not in seen_news and TELEGRAM_TAPE_CHANNEL:
                if await send(bot, TELEGRAM_TAPE_CHANNEL, fmt(a)): seen_news.add(nid); await asyncio.sleep(MESSAGE_DELAY)
        while True:
            await asyncio.sleep(60)
            try:
                d = load_data()
                for a in (await fetch_news(s,d.get("watchlist",[]),20)) + (await fetch_keyword_news(s,d.get("keywords",[]),30)):
                    nid = a.get('benzinga_id') or a.get('id')
                    if nid and nid not in seen_news and TELEGRAM_TAPE_CHANNEL:
                        if await send(bot, TELEGRAM_TAPE_CHANNEL, fmt(a)): seen_news.add(nid); await asyncio.sleep(MESSAGE_DELAY)
                if len(seen_news)>10000: seen_news.clear()
            except Exception as e: print(f"Err: {e}"); await asyncio.sleep(30)

async def start(u: Update, c): await u.message.reply_text("Running!")
async def post_init(app): asyncio.create_task(loop(app))

def main():
    if not BENZINGA_API_KEY or not TELEGRAM_BOT_TOKEN: print("Missing env!"); return
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__': main()
