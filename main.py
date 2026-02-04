#!/usr/bin/env python3
"""Real-Time News Bot with Benzinga API"""
import asyncio
import aiohttp
import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_WATCHLIST = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")

DATA_FILE = "/tmp/newsbot_data.json"
seen_news = set()

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('tickers', [])), set(data.get('keywords', []))
    except:
        pass
    tickers = set(s.strip().upper() for s in INITIAL_WATCHLIST.split(',') if s.strip())
    keywords = set(s.strip().upper() for s in INITIAL_KEYWORDS.split(',') if s.strip())
    return tickers, keywords

def save_data(tickers, keywords):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({'tickers': list(tickers), 'keywords': list(keywords)}, f)
    except Exception as e:
        print(f"Error: {e}")

tickers, keywords = load_data()

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tickers
    if not context.args:
        await update.message.reply_text("Usage: /add TICKER")
        return
    added = [s.strip().upper() for s in context.args if s.strip().upper() not in tickers]
    for s in added:
        tickers.add(s)
    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Added: {', '.join(added)}")

async def cmd_addkw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global keywords
    if not context.args:
        await update.message.reply_text("Usage: /addkw KEYWORD")
        return
    added = [s.strip().upper() for s in context.args if s.strip().upper() not in keywords]
    for s in added:
        keywords.add(s)
    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Added: {', '.join(added)}")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tickers
    removed = [s.strip().upper() for s in context.args if s.strip().upper() in tickers]
    for s in removed:
        tickers.remove(s)
    if removed:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Removed: {', '.join(removed)}")

async def cmd_removekw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global keywords
    removed = [s.strip().upper() for s in context.args if s.strip().upper() in keywords]
    for s in removed:
        keywords.remove(s)
    if removed:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Removed: {', '.join(removed)}")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"Tickers: {', '.join(sorted(tickers))}\nKeywords: {', '.join(sorted(keywords))}"
    await update.message.reply_text(msg or "Empty")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/add /addkw /remove /removekw /list /help")

async def fetch_news(session, tickers_list=None, size=20):
    url = "https://api.benzinga.com/api/v2/news"
    params = {"token": BENZINGA_API_KEY, "pageSize": size, "displayOutput": "full"}
    if tickers_list:
        params["tickers"] = ",".join(tickers_list)
    try:
        async with session.get(url, params=params) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        print(f"Error: {e}")
    return []

async def send_msg(bot, text):
    if TELEGRAM_TAPE_CHANNEL:
        try:
            await bot.send_message(chat_id=TELEGRAM_TAPE_CHANNEL, text=text, parse_mode='HTML', disable_web_page_preview=True)
        except:
            pass

async def news_loop(bot):
    print("Starting Benzinga loop...")
    async with aiohttp.ClientSession() as s:
        while True:
            ct, ck = list(tickers), list(keywords)
            if ct:
                for i in range(0, len(ct), 10):
                    batch = ct[i:i+10]
                    for item in await fetch_news(s, batch, 15):
                        title, nid = item.get('title', ''), item.get('id', '')
                        if nid in seen_news or len(title) < 20:
                            continue
                        seen_news.add(nid)
                        sym = batch[0]
                        for st in item.get('stocks', []):
                            if st.get('name', '').upper() in [x.upper() for x in batch]:
                                sym = st.get('name', '').upper()
                                break
                        await send_msg(bot, f"<b>${sym}</b>\n{title}")
                        print(f"[BZ] ${sym} {title[:40]}")
                    await asyncio.sleep(0.2)
            if ck:
                for item in await fetch_news(s, size=30):
                    title, nid = item.get('title', ''), item.get('id', '')
                    if nid in seen_news or len(title) < 20:
                        continue
                    text = title + item.get('teaser', '')
                    for kw in ck:
                        if kw.lower() in text.lower():
                            seen_news.add(nid)
                            await send_msg(bot, f"<b>[KW] {kw}</b>\n{title}")
                            print(f"[KW] {kw} {title[:40]}")
                            break
            if len(seen_news) > 5000:
                seen_news.clear()
            await asyncio.sleep(60)

async def main():
    print("Starting Benzinga Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    for cmd, fn in [("add", cmd_add), ("addkw", cmd_addkw), ("remove", cmd_remove), ("removekw", cmd_removekw), ("list", cmd_list), ("help", cmd_help), ("start", cmd_help)]:
        app.add_handler(CommandHandler(cmd, fn))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        await news_loop(app.bot)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
