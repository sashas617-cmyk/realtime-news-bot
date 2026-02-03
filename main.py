#!/usr/bin/env python3
"""Real-Time News Bot with Telegram Command Support"""
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

# Persistent storage file
WATCHLIST_FILE = "/tmp/watchlist.json"
seen_news = set()

def load_watchlist():
    """Load watchlist from file or environment"""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                return set(json.load(f))
    except:
        pass
    # Fall back to environment variable
    return set(s.strip().upper() for s in INITIAL_WATCHLIST.split(',') if s.strip())

def save_watchlist(watchlist):
    """Save watchlist to file"""
    try:
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(list(watchlist), f)
    except Exception as e:
        print(f"Error saving watchlist: {e}")

# Global watchlist
watchlist = load_watchlist()

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add symbol(s) to watchlist: /add AAPL TSLA"""
    global watchlist
    if not context.args:
        await update.message.reply_text("Usage: /add SYMBOL [SYMBOL2 ...]")
        return

    added = []
    for symbol in context.args:
        sym = symbol.strip().upper()
        if sym and sym not in watchlist:
            watchlist.add(sym)
            added.append(sym)

    if added:
        save_watchlist(watchlist)
        await update.message.reply_text(f"Added: {', '.join(added)}
Watchlist now has {len(watchlist)} symbols.")
    else:
        await update.message.reply_text("No new symbols added (already in watchlist or invalid).")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove symbol(s) from watchlist: /remove AAPL"""
    global watchlist
    if not context.args:
        await update.message.reply_text("Usage: /remove SYMBOL [SYMBOL2 ...]")
        return

    removed = []
    for symbol in context.args:
        sym = symbol.strip().upper()
        if sym in watchlist:
            watchlist.remove(sym)
            removed.append(sym)

    if removed:
        save_watchlist(watchlist)
        await update.message.reply_text(f"Removed: {', '.join(removed)}
Watchlist now has {len(watchlist)} symbols.")
    else:
        await update.message.reply_text("No symbols removed (not in watchlist).")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current watchlist: /list"""
    if watchlist:
        symbols = sorted(watchlist)
        await update.message.reply_text(f"Watchlist ({len(symbols)} symbols):
{', '.join(symbols)}")
    else:
        await update.message.reply_text("Watchlist is empty. Use /add SYMBOL to add stocks.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help: /help"""
    help_text = """
<b>News Bot Commands</b>

/add SYMBOL - Add stock(s) to watchlist
/remove SYMBOL - Remove stock(s) from watchlist
/list - Show current watchlist
/help - Show this help

<b>Examples:</b>
/add AAPL TSLA NVDA
/remove META
/list
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def fetch_news(session, symbol):
    """Fetch news for a symbol from Finnhub"""
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
            current_watchlist = list(watchlist)  # Copy to avoid modification during iteration
            new_count = 0

            for symbol in current_watchlist:
                news = await fetch_news(session, symbol)
                for item in news[:3]:
                    news_id = f"{item.get('headline','')}_{item.get('datetime','')}"
                    if news_id not in seen_news:
                        seen_news.add(news_id)
                        headline = item.get('headline', '')
                        msg = f"<b>${symbol}</b>
{headline}"
                        if TELEGRAM_TAPE_CHANNEL:
                            await send_telegram(bot, TELEGRAM_TAPE_CHANNEL, msg)
                            print(f"Posted: {symbol} - {headline[:50]}")
                            new_count += 1
                await asyncio.sleep(0.1)  # Small delay between symbols

            if new_count == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Checked {len(current_watchlist)} symbols - no new news")

            await asyncio.sleep(60)  # Check every minute

async def main():
    """Main entry point"""
    print("Starting Real-Time News Bot...")
    print(f"Initial watchlist: {sorted(watchlist)}")

    # Create bot application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
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
