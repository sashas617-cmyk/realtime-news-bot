"""
Configuration for Real-Time News Bot
"""
import os

# Finnhub API
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BREAKING_CHANNEL = os.environ.get("TELEGRAM_BREAKING_CHANNEL", "")
TELEGRAM_TAPE_CHANNEL = os.environ.get("TELEGRAM_TAPE_CHANNEL", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

# LLM for filtering
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude")

# Default watchlist
DEFAULT_WATCHLIST = [
      "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
      "JPM", "BAC", "GS", "V", "MA",
      "XOM", "CVX", "COP",
      "SPY", "QQQ", "DIA"
]

NEWS_POLL_INTERVAL = 30
IMPORTANCE_THRESHOLD = 7
