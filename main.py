#!/usr/bin/env python3
"""Real-Time News Bot with Ticker + Keyword Support"""
import asyncio
import aiohttp
import os
import json
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration from environment
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_WATCHLIST = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")

# Persistent storage
DATA_FILE = "/tmp/newsbot_data.json"
seen_news = set()

def load_data():
    """Load tickers and keywords from file or environment"""
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
    """Save tickers and keywords to file"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump({'tickers': list(tickers), 'keywords': list(keywords)}, f)
    except Exception as e:
        print(f"Error saving data: {e}")

tickers, keywords = load_data()

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tickers
    if not context.args:
        await update.message.reply_text("Usage: /add TICKER [TICKER2 ...]
Example: /add AAPL MSFT CLSK")
        return
    added = []
    for symbol in context.args:
        sym = symbol.strip().upper()
        if sym and sym not in tickers:
            tickers.add(sym)
            added.append(sym)
    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Added tickers: {', '.join(added)}
Total: {len(tickers)} tickers")
    else:
        await update.message.reply_text("No new tickers added.")

async def cmd_addkw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global keywords
    if not context.args:
        await update.message.reply_text("Usage: /addkw KEYWORD [KEYWORD2 ...]
Example: /addkw TRUMP GOLD SILVER")
        return
    added = []
    for kw in context.args:
        k = kw.strip().upper()
        if k and k not in keywords:
            keywords.add(k)
            added.append(k)
    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Added keywords: {', '.join(added)}
Total: {len(keywords)} keywords")
    else:
        await update.message.reply_text("No new keywords added.")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global tickers
    if not context.args:
        await update.message.reply_text("Usage: /remove TICKER [TICKER2 ...]")
        return
    removed = []
    for symbol in context.args:
        sym = symbol.strip().upper()
        if sym in tickers:
            tickers.remove(sym)
            removed.append(sym)
    if removed:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Removed tickers: {', '.join(removed)}
Total: {len(tickers)} tickers")
    else:
        await update.message.reply_text("No tickers removed.")

async def cmd_removekw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global keywords
    if not context.args:
        await update.message.reply_text("Usage: /removekw KEYWORD [KEYWORD2 ...]")
        return
    removed = []
    for kw in context.args:
        k = kw.strip().upper()
        if k in keywords:
            keywords.remove(k)
            removed.append(k)
    if removed:
        save_data(tickers, keywords)
        await update.message.reply_text(f"Removed keywords: {', '.join(removed)}
Total: {len(keywords)} keywords")
    else:
        await update.message.reply_text("No keywords removed.")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ""
    if tickers:
        msg += f"<b>Tickers ({len(tickers)}):</b>
{', '.join(sorted(tickers))}

"
    if keywords:
        msg += f"<b>Keywords ({len(keywords)}):</b>
{', '.join(sorted(keywords))}"
    if not msg:
        msg = "Nothing tracked yet.
Use /add for tickers, /addkw for keywords."
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
<b>News Bot Commands</b>

<b>Tickers (company news):</b>
/add AAPL MSFT - Add stock tickers
/remove TSLA - Remove tickers

<b>Keywords (search all news):</b>
/addkw TRUMP GOLD - Add keywords
/removekw SILVER - Remove keywords

<b>Other:</b>
/list - Show what you're tracking
/help - Show this help

<b>Examples:</b>
/add AAPL MSFT CLSK RIOT
/addkw TRUMP GOLD SILVER
/list
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def fetch_company_news(session, symbol):
    today = datetime.now()
    from_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={from_date}&to={today.strftime('%Y-%m-%d')}&token={FINNHUB_API_KEY}"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
    return []

async def fetch_general_news(session, category="general"):
    url = f"https://finnhub.io/api/v1/news?category={category}&token={FINNHUB_API_KEY}"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"Error fetching general news: {e}")
    return []

def matches_keyword(text, keyword):
    return keyword.lower() in text.lower()

async def send_telegram(bot, channel, text):
    try:
        await bot.send_message(chat_id=channel, text=text, parse_mode='HTML')
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

async def news_loop(bot):
    print("Starting news loop...")
    async with aiohttp.ClientSession() as session:
        while True:
            new_count = 0
            current_tickers = list(tickers)
            for symbol in current_tickers:
                news = await fetch_company_news(session, symbol)
                for item in news[:3]:
                    news_id = f"{item.get('headline','')}_{item.get('datetime','')}"
                    if news_id not in seen_news:
                        seen_news.add(news_id)
                        headline = item.get('headline', '')
                        msg = f"<b>${symbol}</b>
{headline}"
                        if TELEGRAM_TAPE_CHANNEL:
                            await send_telegram(bot, TELEGRAM_TAPE_CHANNEL, msg)
                            print(f"Posted: ${symbol} - {headline[:50]}")
                            new_count += 1
                await asyncio.sleep(0.1)

            current_keywords = list(keywords)
            if current_keywords:
                general_news = await fetch_general_news(session)
                for item in general_news[:20]:
                    headline = item.get('headline', '')
                    summary = item.get('summary', '')
                    text_to_search = f"{headline} {summary}"
                    for kw in current_keywords:
                        if matches_keyword(text_to_search, kw):
                            news_id = f"{headline}_{item.get('datetime','')}"
                            if news_id not in seen_news:
                                seen_news.add(news_id)
                                msg = f"<b>{kw}</b>
{headline}"
                                if TELEGRAM_TAPE_CHANNEL:
                                    await send_telegram(bot, TELEGRAM_TAPE_CHANNEL, msg)
                                    print(f"Posted: {kw} match - {headline[:50]}")
                                    new_count += 1
                            break

            if new_count == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Checked {len(current_tickers)} tickers, {len(current_keywords)} keywords - no new news")
            await asyncio.sleep(60)

async def main():
    print("Starting Real-Time News Bot...")
    print(f"Tickers: {sorted(tickers)}")
    print(f"Keywords: {sorted(keywords)}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("addkw", cmd_addkw))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("removekw", cmd_removekw))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))

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
