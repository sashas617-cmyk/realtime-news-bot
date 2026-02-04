#!/usr/bin/env python3
"""Real-Time News Bot with Benzinga API - v3 with Rate Limiting Fix"""
import asyncio
import aiohttp
import os
import json
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import RetryAfter

BENZINGA_API_KEY = os.environ.get("BENZINGA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
INITIAL_WATCHLIST = os.environ.get("WATCHLIST", "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,SPY,QQQ")
INITIAL_KEYWORDS = os.environ.get("KEYWORDS", "")

# Rate limiting: minimum seconds between messages
MESSAGE_DELAY = 2.0

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

def clean_html(text):
    """Remove HTML tags from text"""
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

async def fetch_news(session, tickers_list=None, size=20):
    url = "https://api.benzinga.com/api/v2/news"
    params = {"token": BENZINGA_API_KEY, "pageSize": size, "displayOutput": "full"}
    headers = {"Accept": "application/json"}
    if tickers_list:
        params["tickers"] = ",".join(tickers_list)
    try:
        async with session.get(url, params=params, headers=headers) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        print(f"Fetch error: {e}")
    return []

def format_message(item, symbol=None, kw_tag=None):
    """Format news item for Telegram with teaser and source"""
    title = clean_html(item.get('title', ''))
    teaser = clean_html(item.get('teaser', ''))
    url = item.get('url', '')
    author = item.get('author', '')

    lines = []

    # Header with symbol or keyword
    if kw_tag:
        lines.append(f"<b>[{kw_tag}]</b>")
    elif symbol:
        lines.append(f"<b>${symbol}</b>")

    # Title
    lines.append(title)

    # Teaser (summary) - if available and different from title
    if teaser and teaser.lower() != title.lower() and len(teaser) > 20:
        if len(teaser) > 200:
            teaser = teaser[:197] + "..."
        lines.append(f"\n{teaser}")

    # Source/Author and link
    if url:
        source = author if author else "Benzinga"
        lines.append(f'\n<a href="{url}">{source}</a>')

    return "\n".join(lines)

async def send_msg(bot, text):
    """Send message with proper rate limit handling"""
    if not TELEGRAM_TAPE_CHANNEL:
        return False

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=TELEGRAM_TAPE_CHANNEL,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            return True
        except RetryAfter as e:
            # Telegram told us to wait - respect it
            wait_time = e.retry_after + 1
            print(f"Rate limited, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            error_str = str(e).lower()
            if "flood" in error_str or "retry" in error_str:
                # Extract wait time if possible, default to 30s
                wait_time = 30
                try:
                    import re
                    match = re.search(r'(\d+)', str(e))
                    if match:
                        wait_time = int(match.group(1)) + 1
                except:
                    pass
                print(f"Flood control, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Send error: {e}")
                return False
    return False

async def news_loop(bot):
    print("Starting Benzinga loop (v3 - rate limited)...")
    print(f"Message delay: {MESSAGE_DELAY}s")
    print(f"Watching tickers: {tickers}")
    print(f"Watching keywords: {keywords}")

    async with aiohttp.ClientSession() as s:
        while True:
            ct, ck = list(tickers), list(keywords)
            messages_sent = 0

            # Fetch news for tickers
            if ct:
                for i in range(0, len(ct), 10):
                    batch = ct[i:i+10]
                    for item in await fetch_news(s, batch, 20):
                        nid = item.get('id', '')
                        title = item.get('title', '')
                        if nid in seen_news or len(title) < 20:
                            continue
                        seen_news.add(nid)

                        # Find matching symbol
                        sym = batch[0]
                        for st in item.get('stocks', []):
                            if st.get('name', '').upper() in [x.upper() for x in batch]:
                                sym = st.get('name', '').upper()
                                break

                        msg = format_message(item, symbol=sym)
                        if await send_msg(bot, msg):
                            print(f"[BZ] ${sym} {title[:50]}")
                            messages_sent += 1

                        # Rate limit delay
                        await asyncio.sleep(MESSAGE_DELAY)

            # Fetch general news for keyword matching
            if ck:
                for item in await fetch_news(s, size=100):
                    nid = item.get('id', '')
                    title = item.get('title', '')
                    if nid in seen_news or len(title) < 20:
                        continue

                    # Check title, teaser, and channels for keywords
                    teaser = item.get('teaser', '')
                    channels = ' '.join([c.get('name', '') for c in item.get('channels', [])])
                    searchable = (title + ' ' + teaser + ' ' + channels).lower()

                    for kw in ck:
                        if kw.lower() in searchable:
                            seen_news.add(nid)
                            msg = format_message(item, kw_tag=kw)
                            if await send_msg(bot, msg):
                                print(f"[KW] {kw} {title[:50]}")
                                messages_sent += 1

                            # Rate limit delay
                            await asyncio.sleep(MESSAGE_DELAY)
                            break

            # Cleanup old seen news
            if len(seen_news) > 5000:
                seen_news.clear()

            # Log cycle completion
            if messages_sent > 0:
                print(f"Cycle complete: {messages_sent} messages sent")

            # Wait before next cycle
            await asyncio.sleep(60)

async def main():
    print("Starting Benzinga Bot v3...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    for cmd, fn in [("add", cmd_add), ("addkw", cmd_addkw),
                    ("remove", cmd_remove), ("removekw", cmd_removekw),
                    ("list", cmd_list), ("help", cmd_help), ("start", cmd_help)]:
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
