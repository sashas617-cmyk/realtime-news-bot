#!/usr/bin/env python3
"""Real-Time News Bot v6 - LOCAL Ticker Filtering + Higher Limits"""
import asyncio
import aiohttp
import os
import json
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import RetryAfter

MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_TICKERS = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")

MESSAGE_DELAY = 2.0
POLL_INTERVAL = 30  # Check every 30 seconds
FETCH_LIMIT = 200   # Get 200 articles to not miss smaller tickers
DATA_FILE = "/tmp/newsbot_data.json"
MASSIVE_API_URL = "https://api.massive.com/benzinga/v2/news"
seen_news = set()

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {
        "tickers": [t.strip().upper() for t in INITIAL_TICKERS.split(",") if t.strip()],
        "keywords": [k.strip().lower() for k in INITIAL_KEYWORDS.split(",") if k.strip()]
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("News Bot v6!\n/tickers /keywords\n/addticker SYMBOL\n/removeticker SYMBOL\n/addkeyword WORD\n/removekeyword WORD")

async def cmd_tickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(f"Tickers: {', '.join(data.get('tickers', []))}")

async def cmd_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(f"Keywords: {', '.join(data.get('keywords', []))}")

async def cmd_addticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addticker SYMBOL")
    ticker = context.args[0].upper()
    data = load_data()
    if ticker not in data["tickers"]:
        data["tickers"].append(ticker)
        save_data(data)
    await update.message.reply_text(f"Added {ticker}. Tickers: {', '.join(data['tickers'])}")

async def cmd_removeticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /removeticker SYMBOL")
    ticker = context.args[0].upper()
    data = load_data()
    if ticker in data["tickers"]:
        data["tickers"].remove(ticker)
        save_data(data)
    await update.message.reply_text(f"Tickers: {', '.join(data['tickers'])}")

async def cmd_addkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /addkeyword WORD")
    kw = ' '.join(context.args).lower()
    data = load_data()
    if kw not in data["keywords"]:
        data["keywords"].append(kw)
        save_data(data)
    await update.message.reply_text(f"Added '{kw}'. Keywords: {', '.join(data['keywords'])}")

async def cmd_removekeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /removekeyword WORD")
    kw = ' '.join(context.args).lower()
    data = load_data()
    if kw in data["keywords"]:
        data["keywords"].remove(kw)
        save_data(data)
    await update.message.reply_text(f"Keywords: {', '.join(data['keywords'])}")

async def fetch_all_news(session, limit=200):
    """Fetch news from Massive.com API - no ticker param (it's broken)"""
    params = {'apiKey': MASSIVE_API_KEY, 'limit': limit, 'sort': 'published.desc'}
    try:
        async with session.get(MASSIVE_API_URL, params=params, headers={'Accept': 'application/json'}) as r:
            if r.status == 200:
                data = await r.json()
                return data.get('results', [])
            print(f"API error: {r.status}")
            return []
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

def matches_ticker(article, tickers):
    """Check if article mentions any of our tickers"""
    if not tickers:
        return False
    article_tickers = article.get('tickers', []) or article.get('stocks', [])
    if not article_tickers:
        return False
    normalized = []
    for t in article_tickers:
        if isinstance(t, dict):
            name = t.get('name', '').upper()
            if name:
                normalized.append(name)
        else:
            normalized.append(str(t).upper())
    return any(ticker.upper() in normalized for ticker in tickers)

def matches_keyword(article, keywords):
    """Check if article contains any of our keywords"""
    if not keywords:
        return False
    text = ((article.get('title') or '') + ' ' + (article.get('teaser') or '')).lower()
    return any(kw.lower() in text for kw in keywords)

def format_msg(a):
    title = a.get('title', 'No title')
    teaser = a.get('teaser', '')
    url = a.get('url', '')
    article_tickers = a.get('tickers', []) or a.get('stocks', [])
    ticker_list = [t.get('name', '') if isinstance(t, dict) else str(t) for t in article_tickers[:5]]
    
    msg = f"<b>{title}</b>"
    if ticker_list:
        msg += f"\n<i>{', '.join(ticker_list)}</i>"
    if teaser:
        msg += f"\n\n{teaser[:300]}"
    if url:
        msg += f'\n<a href="{url}">Read</a>'
    return msg

async def send_msg(bot, text):
    if not TELEGRAM_TAPE_CHANNEL:
        return False
    for _ in range(3):
        try:
            await bot.send_message(chat_id=TELEGRAM_TAPE_CHANNEL, text=text, parse_mode='HTML', disable_web_page_preview=True)
            return True
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            if "flood" in str(e).lower():
                await asyncio.sleep(30)
            else:
                print(f"Send error: {e}")
                return False
    return False

async def news_loop(app):
    global seen_news
    bot = app.bot
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                data = load_data()
                tickers = data.get('tickers', [])
                keywords = data.get('keywords', [])
                
                all_articles = await fetch_all_news(session, FETCH_LIMIT)
                print(f"Fetched {len(all_articles)} articles")
                
                # LOCAL FILTERING
                matched = 0
                for a in all_articles:
                    nid = a.get('benzinga_id') or a.get('id')
                    if not nid or nid in seen_news:
                        continue
                    
                    if matches_ticker(a, tickers) or matches_keyword(a, keywords):
                        if await send_msg(bot, format_msg(a)):
                            seen_news.add(nid)
                            matched += 1
                            # Show which ticker matched
                            article_tickers = a.get('tickers', []) or a.get('stocks', [])
                            ticker_names = [t.get('name') if isinstance(t, dict) else t for t in article_tickers]
                            print(f"MATCH: {ticker_names} - {a.get('title', '')[:40]}")
                            await asyncio.sleep(MESSAGE_DELAY)
                
                if matched:
                    print(f"Sent {matched} matching articles")
                
                if len(seen_news) > 10000:
                    seen_news.clear()
                    
            except Exception as e:
                print(f"Loop error: {e}")
            
            await asyncio.sleep(POLL_INTERVAL)

async def post_init(app):
    asyncio.create_task(news_loop(app))

def main():
    if not MASSIVE_API_KEY or not TELEGRAM_BOT_TOKEN:
        print("Missing MASSIVE_API_KEY or TELEGRAM_BOT_TOKEN!")
        return

    data = load_data()
    print(f"Tickers: {data.get('tickers', [])}")
    print(f"Keywords: {data.get('keywords', [])}")
    print(f"Polling every {POLL_INTERVAL}s, fetching {FETCH_LIMIT} articles")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tickers", cmd_tickers))
    app.add_handler(CommandHandler("keywords", cmd_keywords))
    app.add_handler(CommandHandler("addticker", cmd_addticker))
    app.add_handler(CommandHandler("removeticker", cmd_removeticker))
    app.add_handler(CommandHandler("addkeyword", cmd_addkeyword))
    app.add_handler(CommandHandler("removekeyword", cmd_removekeyword))

    print("Bot v6 starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
