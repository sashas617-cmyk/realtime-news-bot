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
    # Fall back to environment variables
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

# Global watchlists
tickers, keywords = load_data()

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add ticker(s): /add AAPL TSLA"""
    global tickers
    if not context.args:
        await update.message.reply_text("Usage: /add TICKER [TICKER2 ...]\nExample: /add AAPL MSFT CLSK")
        return

    added = []
    for symbol in context.args:
        sym = symbol.strip().upper()
        if sym and sym not in tickers:
            tickers.add(sym)
            added.append(sym)

    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"â Added tickers: {', '.join(added)}\nTotal: {len(tickers)} tickers")
    else:
        await update.message.reply_text("No new tickers added (already tracking).")

async def cmd_addkw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add keyword(s): /addkw TRUMP GOLD"""
    global keywords
    if not context.args:
        await update.message.reply_text("Usage: /addkw KEYWORD [KEYWORD2 ...]\nExample: /addkw TRUMP GOLD SILVER")
        return

    added = []
    for kw in context.args:
        k = kw.strip().upper()
        if k and k not in keywords:
            keywords.add(k)
            added.append(k)

    if added:
        save_data(tickers, keywords)
        await update.message.reply_text(f"â Added keywords: {', '.join(added)}\nTotal: {len(keywords)} keywords")
    else:
        await update.message.reply_text("No new keywords added (already tracking).")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove ticker(s): /remove AAPL"""
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
        await update.message.reply_text(f"â Removed tickers: {', '.join(removed)}\nTotal: {len(tickers)} tickers")
    else:
        await update.message.reply_text("No tickers removed (not in list).")

async def cmd_removekw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove keyword(s): /removekw TRUMP"""
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
        await update.message.reply_text(f"â Removed keywords: {', '.join(removed)}\nTotal: {len(keywords)} keywords")
    else:
        await update.message.reply_text("No keywords removed (not in list).")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current watchlist: /list"""
    msg = ""
    if tickers:
        msg += f"<b>ð Tickers ({len(tickers)}):</b>\n{', '.join(sorted(tickers))}\n\n"
    if keywords:
        msg += f"<b>ð Keywords ({len(keywords)}):</b>\n{', '.join(sorted(keywords))}"
    if not msg:
        msg = "Nothing tracked yet.\nUse /add for tickers, /addkw for keywords."
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help: /help"""
    help_text = """
<b>ð° News Bot Commands</b>

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
    """Fetch news for a specific stock ticker"""
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
    """Fetch general market news"""
    url = f"https://finnhub.io/api/v1/news?category={category}&token={FINNHUB_API_KEY}"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        print(f"Error fetching general news: {e}")
    return []

def matches_keyword(text, keyword):
    """Check if keyword appears in text (case-insensitive)"""
    return keyword.lower() in text.lower()

async def send_telegram(bot, channel, text):
    """Send message to Telegram channel"""
    try:
        await bot.send_message(chat_id=channel, text=text, parse_mode='HTML')
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

async def news_loop(bot):
    """Main loop to fetch and post news"""
    print("Starting news loop...")
    async with aiohttp.ClientSession() as session:
        while True:
            new_count = 0

            # 1. Fetch company news for each ticker
            current_tickers = list(tickers)
            for symbol in current_tickers:
                news = await fetch_company_news(session, symbol)
                for item in news[:3]:
                    news_id = f"{item.get('headline','')}_{item.get('datetime','')}"
                    if news_id not in seen_news:
                        seen_news.add(news_id)
                        headline = item.get('headline', '')
                        msg = f"<b>${symbol}</b>\n{headline}"
                        if TELEGRAM_TAPE_CHANNEL:
                            await send_telegram(bot, TELEGRAM_TAPE_CHANNEL, msg)
                            print(f"Posted: ${symbol} - {headline[:50]}")
                            new_count += 1
                await asyncio.sleep(0.1)

            # 2. Fetch general news and filter by keywords
            current_keywords = list(keywords)
            if current_keywords:
                general_news = await fetch_general_news(session)
                for item in general_news[:20]:  # Check top 20 general news
                    headline = item.get('headline', '')
                    summary = item.get('summary', '')
                    text_to_search = f"{headline} {summary}"

                    # Check each keyword
                    for kw in current_keywords:
                        if matches_keyword(text_to_search, kw):
                            news_id = f"{headline}_{item.get('datetime','')}"
                            if news_id not in seen_news:
                                seen_news.add(news_id)
                                msg = f"<b>ð {kw}</b>\n{headline}"
                                if TELEGRAM_TAPE_CHANNEL:
                                    await send_telegram(bot, TELEGRAM_TAPE_CHANNEL, msg)
                                    print(f"Posted: {kw} match - {headline[:50]}")
                                    new_count += 1
                            break  # Don't post same news for multiple keyword matches

            if new_count == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Checked {len(current_tickers)} tickers, {len(current_keywords)} keywords - no new news")

            await asyncio.sleep(60)  # Check every minute

async def main():
    """Main entry point"""
    print("Starting Real-Time News Bot...")
    print(f"Tickers: {sorted(tickers)}")
    print(f"Keywords: {sorted(keywords)}")

    # Create bot application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("addkw", cmd_addkw))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("removekw", cmd_removekw))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))

    # Initialize the bot
    await app.initialize()
    await app.start()

    # Start polling for commands in background
    await app.updater.start_polling(drop_pending_updates=True)

    # Run news loop (this blocks)
    try:
        await news_loop(app.bot)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
