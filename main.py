#!/usr/bin/env python3
"""Real-Time News Bot with Massive.com API - v5 Fixed"""
import asyncio
import aiohttp
import os
import re
from datetime import datetime
from telegram import Bot
from telegram.error import RetryAfter

BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
TICKERS = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ").split(",")
KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]

MESSAGE_DELAY = 2.0
MASSIVE_API_URL = "https://api.massive.com/benzinga/v2/news"
seen_news = set()

async def fetch_news(session, tickers=None, limit=50):
    params = {'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}
    if tickers:
        params['tickers'] = ','.join(tickers)
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

async def fetch_keyword_news(session, keywords, limit=100):
    if not keywords:
        return []
    try:
        async with session.get(MASSIVE_API_URL, params={'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}, headers={'Accept': 'application/json'}) as r:
            if r.status != 200:
                return []
            data = await r.json()
            articles = data.get('results', [])
            filtered = []
            for a in articles:
                text = ((a.get('title') or '') + ' ' + (a.get('teaser') or '')).lower()
                if any(kw in text for kw in keywords):
                    filtered.append(a)
            return filtered
    except:
        return []

def format_msg(a):
    title = a.get('title', 'No title')
    teaser = a.get('teaser', '')
    author = a.get('author', '')
    url = a.get('url', '')
    tickers = a.get('tickers', [])
    ticker_str = ', '.join(tickers[:5]) if tickers else ''
    
    msg = f"<b>{title}</b>"
    if ticker_str:
        msg += f"\n<i>Tickers: {ticker_str}</i>"
    if teaser:
        msg += f"\n\n{teaser[:300]}"
    if author:
        msg += f"\n<i>By {author}</i>"
    if url:
        msg += f'\n<a href="{url}">Read more</a>'
    return msg

async def send_msg(bot, text):
    if not TELEGRAM_TAPE_CHANNEL:
        return False
    for _ in range(3):
        try:
            await bot.send_message(chat_id=TELEGRAM_TAPE_CHANNEL, text=text, parse_mode='HTML', disable_web_page_preview=True)
            return True
        except RetryAfter as e:
            print(f"Rate limited, wait {e.retry_after}s")
            await asyncio.sleep(e.retry_after + 1)
        except Exception as e:
            if "flood" in str(e).lower():
                await asyncio.sleep(30)
            else:
                print(f"Send error: {e}")
                return False
    return False

async def main():
    global seen_news
    print("=" * 50)
    print("News Bot v5 - Massive.com API")
    print(f"Tickers: {TICKERS}")
    print(f"Keywords: {KEYWORDS}")
    print("=" * 50)
    
    if not BENZINGA_API_KEY or not TELEGRAM_BOT_TOKEN:
        print("ERROR: Missing API keys!")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
"""Real-Time News Bot with Massive.com API - v5 with TG Commands"""
import asyncio
import aiohttp
import os
import json
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import RetryAfter

BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_TICKERS = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")

MESSAGE_DELAY = 2.0
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
        "tickers": [t.strip() for t in INITIAL_TICKERS.split(",") if t.strip()],
        "keywords": [k.strip().lower() for k in INITIAL_KEYWORDS.split(",") if k.strip()]
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# Telegram Commands
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("News Bot running!\n/tickers - list tickers\n/keywords - list keywords\n/addticker SYMBOL\n/removeticker SYMBOL\n/addkeyword WORD\n/removekeyword WORD")

async def cmd_tickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tickers = data.get("tickers", [])
    await update.message.reply_text(f"Tickers: {', '.join(tickers)}" if tickers else "No tickers set")

async def cmd_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    keywords = data.get("keywords", [])
    await update.message.reply_text(f"Keywords: {', '.join(keywords)}" if keywords else "No keywords set")

async def cmd_addticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addticker SYMBOL")
        return
    ticker = context.args[0].upper()
    data = load_data()
    if ticker not in data["tickers"]:
        data["tickers"].append(ticker)
        save_data(data)
        await update.message.reply_text(f"Added {ticker}")
    else:
        await update.message.reply_text(f"{ticker} already exists")

async def cmd_removeticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removeticker SYMBOL")
        return
    ticker = context.args[0].upper()
    data = load_data()
    if ticker in data["tickers"]:
        data["tickers"].remove(ticker)
        save_data(data)
        await update.message.reply_text(f"Removed {ticker}")
    else:
        await update.message.reply_text(f"{ticker} not found")

async def cmd_addkeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addkeyword WORD")
        return
    keyword = ' '.join(context.args).lower()
    data = load_data()
    if keyword not in data["keywords"]:
        data["keywords"].append(keyword)
        save_data(data)
        await update.message.reply_text(f"Added '{keyword}'")
    else:
        await update.message.reply_text(f"'{keyword}' already exists")

async def cmd_removekeyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removekeyword WORD")
        return
    keyword = ' '.join(context.args).lower()
    data = load_data()
    if keyword in data["keywords"]:
        data["keywords"].remove(keyword)
        save_data(data)
        await update.message.reply_text(f"Removed '{keyword}'")
    else:
        await update.message.reply_text(f"'{keyword}' not found")

# News Functions
async def fetch_news(session, tickers=None, limit=50):
    params = {'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}
    if tickers:
        params['tickers'] = ','.join(tickers)
    try:
        async with session.get(MASSIVE_API_URL, params=params, headers={'Accept': 'application/json'}) as r:
            if r.status == 200:
                return (await r.json()).get('results', [])
            print(f"API error: {r.status}")
            return []
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

async def fetch_keyword_news(session, keywords, limit=100):
    if not keywords:
        return []
    try:
        async with session.get(MASSIVE_API_URL, params={'apiKey': BENZINGA_API_KEY, 'limit': limit, 'sort': 'published.desc'}, headers={'Accept': 'application/json'}) as r:
            if r.status != 200:
                return []
            articles = (await r.json()).get('results', [])
            return [a for a in articles if any(kw in ((a.get('title') or '')+(a.get('teaser') or '')).lower() for kw in keywords)]
    except:
        return []

def format_msg(a):
    title = a.get('title', 'No title')
    teaser = a.get('teaser', '')
    author = a.get('author', '')
    url = a.get('url', '')
    tickers = a.get('tickers', [])
    ticker_str = ', '.join(tickers[:5]) if tickers else ''
    msg = f"<b>{title}</b>"
    if ticker_str:
        msg += f"\n<i>Tickers: {ticker_str}</i>"
    if teaser:
        msg += f"\n\n{teaser[:300]}"
    if author:
        msg += f"\n<i>By {author}</i>"
    if url:
        msg += f'\n<a href="{url}">Read more</a>'
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
    data = load_data()
    print(f"Starting: tickers={data['tickers']}, keywords={data['keywords']}")
    
    async with aiohttp.ClientSession() as session:
        # Initial fetch
        ticker_news = await fetch_news(session, data['tickers'], 30)
        keyword_news = await fetch_keyword_news(session, data['keywords'], 50)
        
        all_news = {}
        for a in ticker_news + keyword_news:
            nid = a.get('benzinga_id')
            if nid and nid not in all_news:
                all_news[nid] = a
        
        print(f"Found {len(all_news)} articles")
        sent = 0
        for nid, a in list(all_news.items())[:25]:
            if nid in seen_news:
                continue
            if await send_msg(bot, format_msg(a)):
                seen_news.add(nid)
                sent += 1
                await asyncio.sleep(MESSAGE_DELAY)
        print(f"Sent {sent} initial")
        
        while True:
            await asyncio.sleep(60)
            try:
                data = load_data()
                ticker_news = await fetch_news(session, data['tickers'], 20)
                keyword_news = await fetch_keyword_news(session, data['keywords'], 30)
                
                new_count = 0
                for a in ticker_news + keyword_news:
                    nid = a.get('benzinga_id')
                    if nid and nid not in seen_news:
                        if await send_msg(bot, format_msg(a)):
                            seen_news.add(nid)
                            new_count += 1
                            await asyncio.sleep(MESSAGE_DELAY)
                
                if new_count > 0:
                    print(f"[{datetime.now()}] Sent {new_count} new")
                if len(seen_news) > 10000:
                    seen_news.clear()
            except Exception as e:
                print(f"Loop error: {e}")
                await asyncio.sleep(30)

async def post_init(app):
    asyncio.create_task(news_loop(app))

def main():
    if not BENZINGA_API_KEY or not TELEGRAM_BOT_TOKEN:
        print("ERROR: Missing env vars!")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tickers", cmd_tickers))
    app.add_handler(CommandHandler("keywords", cmd_keywords))
    app.add_handler(CommandHandler("addticker", cmd_addticker))
    app.add_handler(CommandHandler("removeticker", cmd_removeticker))
    app.add_handler(CommandHandler("addkeyword", cmd_addkeyword))
    app.add_handler(CommandHandler("removekeyword", cmd_removekeyword))
    
    print("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
