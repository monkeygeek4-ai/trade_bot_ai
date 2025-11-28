# Code review marker
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Bybit
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "False").lower() == "true"

# AI (Hugging Face)
HF_TOKEN = os.getenv("HF_TOKEN")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-ai/DeepSeek-V3.2-Exp:novita")

# AI (DeepSeek, прямое подключение)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Perplexity (News & Market Sentiment)
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Риск-менеджмент
# Доля капитала под риск в одной сделке/день (0.02 = 2%, 0.2 = 20%)
try:
    AUTO_RISK_PER_TRADE = float(os.getenv("AUTO_RISK_PER_TRADE", "0.02"))
except ValueError:
    AUTO_RISK_PER_TRADE = 0.02

# Максимальное количество одновременных позиций
try:
    AUTO_MAX_ACTIVE_POSITIONS = int(os.getenv("AUTO_MAX_ACTIVE_POSITIONS", "3"))
except ValueError:
    AUTO_MAX_ACTIVE_POSITIONS = 3

# Database
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Bot name (для различения ботов в БД)
BOT_NAME = os.getenv("BOT_NAME", "main")

# Валидация обязательных переменных
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env файле")
if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise ValueError("BYBIT_API_KEY и BYBIT_API_SECRET должны быть установлены в .env файле")

# Требуем хотя бы один источник AI: HF или DeepSeek
if not HF_TOKEN and not DEEPSEEK_API_KEY:
    raise ValueError("Нужен либо HF_TOKEN, либо DEEPSEEK_API_KEY в .env файле")

