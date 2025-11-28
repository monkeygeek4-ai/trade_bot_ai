import logging
import json
# Code review: Full project analysis
import asyncio
import math
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, JobQueue
from types import SimpleNamespace
import config
from services.bybit_service import BybitService
from services.ai_service import AIService
from services.trading_decision_service import TradingDecisionService
from services.risk_management_service import RiskManagementService
from services.market_analysis_service import MarketAnalysisService
from services.news_service import NewsService
from services.db_service import DatabaseService

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация сервисов
try:
    logger.info("Инициализация сервисов...")
    # Сначала инициализируем БД (если доступна), затем передаем в сервисы
    db_service = None
    try:
        if config.DB_HOST and config.DB_NAME:
            db_service = DatabaseService()
            if db_service.connection and db_service.connection.is_connected():
                db_service.init_tables()
                logger.info("✅ База данных подключена и таблицы инициализированы")
            else:
                logger.warning("⚠️ Не удалось подключиться к БД - история не будет сохраняться")
                db_service = None
        else:
            logger.info("ℹ️ Параметры БД не указаны - история не будет сохраняться")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при инициализации БД: {e} - история не будет сохраняться")
        db_service = None
    
    bybit_service = BybitService(db_service=db_service)  # Передаем db_service для сохранения ошибок
    logger.info("BybitService инициализирован")
    ai_service = AIService()
    logger.info("AIService инициализирован")
    trading_decision_service = TradingDecisionService()
    logger.info("TradingDecisionService инициализирован")
    risk_management_service = RiskManagementService(db_service=db_service)
    logger.info("RiskManagementService инициализирован")
    # Инициализация NewsService (может быть None если API ключ не установлен)
    news_service = None
    try:
        if config.PERPLEXITY_API_KEY:
            news_service = NewsService(api_key=config.PERPLEXITY_API_KEY)
            logger.info("NewsService инициализирован")
        else:
            logger.warning("PERPLEXITY_API_KEY не установлен - новостной анализ недоступен")
    except Exception as e:
        logger.warning(f"Не удалось инициализировать NewsService: {e}")
    
    market_analysis_service = MarketAnalysisService(news_service=news_service, db_service=db_service)
    logger.info("MarketAnalysisService инициализирован")
    
    # Проверяем разрешенные chat_id
    allowed_chat_ids = []
    if config.TELEGRAM_CHAT_ID:
        allowed_chat_ids = [int(cid.strip()) for cid in config.TELEGRAM_CHAT_ID.split(',') if cid.strip()]
        logger.info(f"Разрешенные Chat ID: {allowed_chat_ids}")
    else:
        logger.warning("TELEGRAM_CHAT_ID не установлен - бот будет отвечать всем")
except Exception as e:
    logger.error(f"Ошибка при инициализации сервисов: {e}", exc_info=True)
    raise

# Глобальная переменная для разрешенных chat_id
ALLOWED_CHAT_IDS = allowed_chat_ids if 'allowed_chat_ids' in locals() else []
MIN_QTY_BY_SYMBOL = {
    # Базовые значения по умолчанию; при старте бота мы стараемся переопределить их
    # реальными фильтрами с Bybit через get_instruments_info.
    "BTCUSDT": 0.001,
    "ETHUSDT": 0.01,
    "BNBUSDT": 0.1,
    "XRPUSDT": 10,
    "SOLUSDT": 0.1,
    "ADAUSDT": 10,
    "DOGEUSDT": 100,
    "AVAXUSDT": 0.1,
    "MATICUSDT": 10,
    "LINKUSDT": 0.1,
    "TONUSDT": 1,
    "TRXUSDT": 10,
    "LTCUSDT": 0.01,
    "NEARUSDT": 1,
    "APTUSDT": 0.1,
    "OPUSDT": 0.1,
    "ARBUSDT": 1,
    "POLUSDT": 10,
    "SEIUSDT": 1,
    "SUIUSDT": 1,
}
QTY_STEP_BY_SYMBOL = {
    "BTCUSDT": 0.001,
    "ETHUSDT": 0.001,
    "BNBUSDT": 0.01,
    "XRPUSDT": 1,
    "SOLUSDT": 0.01,
    "ADAUSDT": 1,
    "DOGEUSDT": 1,
    # Для AVAXUSDT шаг лота 0.1, поэтому округляем к 0.1
    "AVAXUSDT": 0.1,
    "MATICUSDT": 1,
    "LINKUSDT": 0.1,
    "TONUSDT": 0.1,
    "TRXUSDT": 1,
    "LTCUSDT": 0.001,
    "NEARUSDT": 0.1,
    "APTUSDT": 0.01,
    "OPUSDT": 0.01,
    "ARBUSDT": 0.1,
    "POLUSDT": 1,
    "SEIUSDT": 0.1,
    "SUIUSDT": 0.1,
}
MAX_ACTIVE_POSITIONS = getattr(config, "AUTO_MAX_ACTIVE_POSITIONS", 3)
AUTO_BUY_JOB_NAME = "auto_buy_job"
AUTO_BUY_INTERVAL_SECONDS = 30
DATA_COLLECTION_JOB_NAME = "data_collection_job"
DATA_COLLECTION_INTERVAL_SECONDS = 60  # Каждую минуту
DATA_ROTATION_JOB_NAME = "data_rotation_job"
DATA_ROTATION_INTERVAL_HOURS = 24  # Раз в день
SIGNAL_TRANSLATIONS = {
    "NEUTRAL": "НЕЙТРАЛЬНЫЙ",
    "N/A": "Н/Д",
    "BULLISH": "БЫЧИЙ",
    "BEARISH": "МЕДВЕЖИЙ",
}
STATUS_TRANSLATIONS = {
    "NEUTRAL": "НЕЙТРАЛЬНО",
    "BALANCED": "СБАЛАНСИРОВАНО",
    "OVERBOUGHT": "ПЕРЕКУПЛЕНО",
    "OVERSOLD": "ПЕРЕПРОДАНО",
}
ORIENTATION_TRANSLATIONS = {
    "LONG": "лонг",
    "SHORT": "шорт",
}


def _translate_signal_value(value: Optional[str], default: str = "НЕЙТРАЛЬНЫЙ") -> str:
    key = (value or "").upper()
    return SIGNAL_TRANSLATIONS.get(key, value if value else default)


def _translate_status_value(value: Optional[str], default: str = "НЕЙТРАЛЬНО") -> str:
    key = (value or "").upper()
    return STATUS_TRANSLATIONS.get(key, value if value else default)


def _translate_orientation(value: Optional[str]) -> str:
    key = (value or "").upper()
    return ORIENTATION_TRANSLATIONS.get(key, value or "позиция")


def _calculate_net_profit(pnl_percent: float, use_maker: bool = True, include_additional_fee: bool = False) -> Dict[str, float]:
    """
    Рассчитать чистую прибыль с учетом комиссий.
    
    Args:
        pnl_percent: Процент прибыли/убытка (например, 0.5 для 0.5%)
        use_maker: Использовать мейкер-комиссию (True) или тейкер (False)
        include_additional_fee: Включать ли дополнительную комиссию 0.05%
    
    Returns:
        Dict с ключами: gross_pnl, entry_fee, exit_fee, additional_fee, total_fees, net_pnl, net_pnl_percent
    """
    entry_fee = MAKER_FEE if use_maker else TAKER_FEE
    exit_fee = TAKER_FEE  # Выход всегда рыночный (стоп/тейк)
    additional_fee = ADDITIONAL_FEE if include_additional_fee else 0.0
    
    total_fees = entry_fee + exit_fee + additional_fee
    net_pnl_percent = pnl_percent - (total_fees * 100)  # Конвертируем в проценты
    
    return {
        "gross_pnl": pnl_percent,
        "entry_fee": entry_fee * 100,  # В процентах
        "exit_fee": exit_fee * 100,
        "additional_fee": additional_fee * 100,
        "total_fees": total_fees * 100,
        "net_pnl": net_pnl_percent,
        "net_pnl_percent": net_pnl_percent
    }


LAST_TRADE_TIMES: Dict[str, datetime] = {}
SYMBOL_FILTERS_REFRESHED = False
MONITOR_JOB_NAME = "active_monitor"
MONITOR_INTERVAL_SECONDS = 300
POSITION_POLL_JOB_NAME = "position_poll"
POSITION_POLL_INTERVAL_SECONDS = 30
TRADE_COOLDOWN_HOURS = 4
# Через сколько секунд после открытия позиции принудительно пересчитать и обновить TP/SL
TP_SL_REFRESH_DELAY_SECONDS = 30
TP_SL_REFRESH_TASKS: Dict[str, asyncio.Task] = {}
DATA_DIR = (Path(__file__).resolve().parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
COOLDOWN_FILE = DATA_DIR / "last_trade_times.json"


def _refresh_symbol_filters_from_exchange():
    """
    Попробовать подтянуть реальные min_qty и qty_step с Bybit для популярных монет.
    Это позволяет избежать ошибок Qty invalid, даже если дефолты в коде отличаются.
    """
    global SYMBOL_FILTERS_REFRESHED
    try:
        symbols = set(MIN_QTY_BY_SYMBOL.keys())
        # Добавляем популярные монеты из MarketAnalysisService (там уже топ-20)
        try:
            mas_symbols = getattr(market_analysis_service, "popular_coins", [])
            symbols.update(mas_symbols)
        except Exception:
            pass

        updated = []
        for sym in sorted(symbols):
            filters = bybit_service.get_symbol_filters(sym)
            if not filters:
                continue
            MIN_QTY_BY_SYMBOL[sym] = filters["min_qty"]
            QTY_STEP_BY_SYMBOL[sym] = filters["qty_step"]
            updated.append(f"{sym}: min={filters['min_qty']}, step={filters['qty_step']}")

        if updated:
            logger.info(
                "Обновлены биржевые фильтры объёма для символов:\n" + "\n".join(updated)
            )
            SYMBOL_FILTERS_REFRESHED = True
    except Exception as e:
        logger.warning(f"Не удалось обновить фильтры объёма с биржи: {e}")


def _load_last_trade_times():
    if not COOLDOWN_FILE.exists():
        return
    try:
        with COOLDOWN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for symbol, iso_time in data.items():
            try:
                LAST_TRADE_TIMES[symbol.upper()] = datetime.fromisoformat(iso_time)
            except ValueError:
                continue
        logger.info(f"Загружено {len(LAST_TRADE_TIMES)} записей карантина из файла.")
    except Exception as e:
        logger.warning(f"Не удалось загрузить файл карантина: {e}")


def _save_last_trade_times():
    try:
        serializable = {symbol: ts.isoformat() for symbol, ts in LAST_TRADE_TIMES.items()}
        with COOLDOWN_FILE.open("w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Не удалось сохранить файл карантина: {e}")


_load_last_trade_times()
_refresh_symbol_filters_from_exchange()


def _record_trade_timestamp(symbol: str, timestamp: Optional[datetime] = None):
    ts = timestamp or datetime.utcnow()
    sym = symbol.upper()
    LAST_TRADE_TIMES[sym] = ts
    logger.info(f"Карантин: {sym} обновлён до {ts.isoformat()}")
    _save_last_trade_times()
AUTO_BUY_STATE = {
    # После перезапуска бота автозакупка сразу включена,
    # чтобы не приходилось каждый раз жать «Авто старт».
    "enabled": True,
    "last_run": None,
    "last_result": "Ещё не запускалась"
}
# Флаг для отслеживания, было ли отправлено уведомление о достижении лимита позиций
LIMIT_NOTIFICATION_SENT = False
def _get_command_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🟢 Купить", callback_data="trade:buy"),
            InlineKeyboardButton("🔴 Продать", callback_data="trade:sell")
        ],
        [
            InlineKeyboardButton("📊 Обзор рынка", callback_data="cmd:market_overview"),
            InlineKeyboardButton("📋 Позиции", callback_data="cmd:positions")
        ],
        [
            InlineKeyboardButton("🎯 Обновить SL/TP", callback_data="cmd:update_tp_sl"),
            InlineKeyboardButton("🔐 Закрыть все", callback_data="cmd:close_all")
        ],
        [
            InlineKeyboardButton("💲 Цена", callback_data="input:price"),
            InlineKeyboardButton("🧠 AI-анализ", callback_data="input:analyze")
        ],
        [
            InlineKeyboardButton("🤖 Авто старт", callback_data="cmd:start_buy"),
            InlineKeyboardButton("✋ Авто стоп", callback_data="cmd:stop_buy"),
            InlineKeyboardButton("ℹ️ Статус авто", callback_data="cmd:auto_status")
        ],
        [
            InlineKeyboardButton("📡 Мониторинг ▶️", callback_data="cmd:monitor_start"),
            InlineKeyboardButton("⏹ Мониторинг стоп", callback_data="cmd:monitor_stop")
        ],
        [
            InlineKeyboardButton("💰 Баланс", callback_data="cmd:balance"),
            InlineKeyboardButton("🆘 Помощь", callback_data="cmd:help")
        ]
    ]
    return InlineKeyboardMarkup(buttons)


# Отслеживание состояния позиций для уведомлений
POSITION_STATES: Dict[str, Dict] = {}  # {symbol: {"last_size": float, "notified_liquidation": bool, "notified_profit": bool, "target_profit": float}}

# Комиссии Bybit (фьючерсы)
MAKER_FEE = 0.0002  # 0.02% для мейкер-ордеров (лимитные)
TAKER_FEE = 0.00055  # 0.055% для тейкер-ордеров (рыночные)
ADDITIONAL_FEE = 0.0005  # 0.05% дополнительная комиссия (если применима)


def check_access(chat_id):
    """Проверка доступа по chat_id"""
    if not ALLOWED_CHAT_IDS:
        return True  # Если список пуст, разрешаем всем
    return chat_id in ALLOWED_CHAT_IDS


def _get_cooldown_remaining(symbol: str) -> Optional[timedelta]:
    last_trade = LAST_TRADE_TIMES.get(symbol.upper())
    if not last_trade:
        return None
    elapsed = datetime.utcnow() - last_trade
    cooldown = timedelta(hours=TRADE_COOLDOWN_HOURS)
    if elapsed >= cooldown:
        return None
    return cooldown - elapsed


def _schedule_tp_sl_refresh(symbol: str):
    """Запустить отложенное обновление TP/SL через 15 секунд после входа."""
    symbol = (symbol or "").upper()
    if not symbol:
        return
    if symbol in TP_SL_REFRESH_TASKS:
        logger.debug(f"TP/SL refresh уже запланирован для {symbol}")
        return

    async def _job():
        try:
            await asyncio.sleep(TP_SL_REFRESH_DELAY_SECONDS)
            await _refresh_tp_sl_for_symbol(symbol)
        except Exception as e:
            logger.error(f"Ошибка при отложенном обновлении TP/SL для {symbol}: {e}", exc_info=True)
        finally:
            TP_SL_REFRESH_TASKS.pop(symbol, None)

    TP_SL_REFRESH_TASKS[symbol] = asyncio.create_task(_job())


async def _refresh_tp_sl_for_symbol(symbol: str):
    """Пересчитать и обновить TP/SL для конкретной позиции."""
    try:
        positions = bybit_service.get_positions() or []
    except Exception as e:
        logger.error(f"Не удалось получить позиции для обновления {symbol}: {e}")
        return

    position = next(
        (pos for pos in positions if (pos.get("symbol") or "").upper() == symbol.upper() and _is_position_active(pos)),
        None
    )
    if not position:
        logger.info(f"Позиция {symbol} не найдена или закрыта — пропускаю обновление TP/SL.")
        return

    data = market_analysis_service.get_historical_data(symbol)
    if not data:
        logger.warning(f"Нет исторических данных для {symbol}, обновление TP/SL пропущено.")
        return

    raw_side = (position.get("side") or "").lower()
    if raw_side == "buy":
        side = "Long"
    elif raw_side == "sell":
        side = "Short"
    else:
        side = "Long" if position.get("positionIdx") in (0, 1) else "Short"

    try:
        entry_price = float(position.get("avgPrice") or position.get("entryPrice") or data.get("current_price", 0))
    except (TypeError, ValueError):
        entry_price = data.get("current_price", 0)

    if entry_price <= 0:
        logger.warning(f"Не удалось определить цену входа для {symbol}, TP/SL не обновлены.")
        return

    volatility_percent = max(data.get("volatility", 2) / 100, 0.01)
    historical = data.get("historical") or {}
    atr = historical.get("atr")
    stop_loss = risk_management_service.get_recommended_stop_loss(entry_price, side, volatility_percent, atr)
    target_gross_pnl = 0.5
    take_profit = entry_price * (1 + target_gross_pnl / 100) if side == "Long" else entry_price * (1 - target_gross_pnl / 100)

    result = bybit_service.update_tp_sl(symbol, stop_loss, take_profit)
    if result.get("stop_loss") or result.get("take_profit"):
        logger.info(f"Отложенное обновление TP/SL выполнено для {symbol}: SL={stop_loss:.4f}, TP={take_profit:.4f}")
    else:
        logger.warning(f"Не удалось обновить TP/SL для {symbol} при отложенном запуске: {result.get('errors')}")


def _normalize_order_qty(symbol: str, qty: float) -> float:
    """Привести количество к допустимому шагу и минимуму биржи."""
    symbol = symbol.upper()
    step = QTY_STEP_BY_SYMBOL.get(symbol, 0.0001)
    min_qty = MIN_QTY_BY_SYMBOL.get(symbol, step)
    if step <= 0:
        step = 0.0001
    normalized = math.floor(qty / step) * step
    if normalized < min_qty:
        normalized = min_qty
    return round(normalized, 6)


async def _broadcast_message(bot, text: str):
    """Отправить одно и то же сообщение во все разрешённые чаты."""
    # Если список не задан, на всякий случай ничего не делаем
    if not ALLOWED_CHAT_IDS:
        return
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=text)


async def _reply_to_all(update: Update, text: str, reply_markup=None):
    """
    Отправить ответ сразу во все ALLOWED_CHAT_IDS.
    Это удобно, когда один и тот же бот обслуживает несколько чатов (как бот Ильи).
    """
    bot = update.get_bot() if hasattr(update, "get_bot") else update.effective_chat.bot
    if not ALLOWED_CHAT_IDS:
        # Fallback: обычный ответ в текущий чат
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup)
        return
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


def _is_position_active(position: Dict) -> bool:
    size_value = position.get("size") or position.get("qty") or position.get("positionSize") or "0"
    try:
        size = float(size_value if size_value not in ("N/A", None, "") else 0)
    except (TypeError, ValueError):
        size = 0
    return abs(size) > 0.0001


def _count_active_positions(positions: Optional[List[Dict]] = None) -> int:
    positions = positions or bybit_service.get_positions() or []
    return sum(1 for pos in positions if _is_position_active(pos))


def _has_active_position(symbol: str, positions: Optional[List[Dict]] = None) -> bool:
    """Проверить, есть ли уже активная позиция по символу."""
    symbol = symbol.upper()
    positions = positions or bybit_service.get_positions() or []
    for pos in positions:
        if (pos.get("symbol", "") or "").upper() == symbol and _is_position_active(pos):
            return True
    return False


def _check_symbol_quarantine(symbol: str, positions: Optional[List[Dict]] = None) -> Optional[str]:
    """Проверить символ на уникальность и карантин."""
    symbol = symbol.upper()
    if positions is None:
        positions = bybit_service.get_positions() or []
    
    remaining = _get_cooldown_remaining(symbol)
    if remaining:
        wait_until = (datetime.utcnow() + remaining).strftime("%H:%M")
        minutes = int(remaining.total_seconds() // 60)
        return (
            f"⏸ {symbol} в карантине ещё {minutes} мин. "
            f"Следующая покупка возможна после {wait_until}."
        )
    
    if _has_active_position(symbol, positions):
        return (
            f"⚠️ По {symbol} уже есть активная позиция. "
            "Дождитесь закрытия текущей сделки или выберите другую монету."
        )
    
    active_count = _count_active_positions(positions)
    if active_count >= MAX_ACTIVE_POSITIONS:
        return (
            f"⚠️ Достигнут лимит {MAX_ACTIVE_POSITIONS} активных сделок. "
            "Закройте текущие позиции или дождитесь их завершения."
        )
    
    return None


def _format_auto_buy_status() -> str:
    status_icon = "🟢" if AUTO_BUY_STATE["enabled"] else "🔴"
    status_text = "активна" if AUTO_BUY_STATE["enabled"] else "остановлена"
    last_run = AUTO_BUY_STATE.get("last_run")
    last_result = AUTO_BUY_STATE.get("last_result", "не запускалась")
    last_run_str = last_run.strftime("%H:%M:%S") if last_run else "—"
    return (
        f"{status_icon} Автозакупка {status_text}\n"
        f"Последний запуск: {last_run_str}\n"
        f"Статус: {last_result}"
    )


class _ContextArgsProxy:
    """Прокси для передачи собственных args в обработчики команд."""
    def __init__(self, base_context, args: List[str]):
        self._base = base_context
        self.args = args
    
    def __getattr__(self, item):
        return getattr(self._base, item)


def _build_callback_update(query) -> SimpleNamespace:
    """Создать Update-подобный объект из callback-query."""
    message = query.message
    return SimpleNamespace(
        message=message,
        effective_chat=message.chat if message else None,
        effective_user=query.from_user
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(f"Получена команда /start от пользователя {user_id}, chat_id: {chat_id}")
    
    # Показываем chat_id пользователю
    chat_info = f"\n\n📋 Ваш Chat ID: {chat_id}\n(Добавьте его в TELEGRAM_CHAT_ID в .env файле)"
    
    # Проверка доступа
    if not check_access(chat_id):
        await update.message.reply_text(f"❌ Доступ запрещен. Ваш Chat ID: {chat_id}")
        logger.warning(f"Попытка доступа с неразрешенного Chat ID: {chat_id}")
        return
    
    try:
        welcome_message = (
            "🤖 Добро пожаловать!\n\n"
            "Все основные действия вынесены в кнопки ниже.\n"
            "Выберите нужный раздел или воспользуйтесь быстрыми кнопками покупки/продажи."
        )
        # Показываем приветствие во всех разрешённых чатах (актуально для Илья-бота)
        await _reply_to_all(update, welcome_message, reply_markup=_get_command_keyboard())
        await _reply_to_all(update, chat_info)
        logger.info("Ответ на /start отправлен успешно")
    except Exception as e:
        logger.error(f"Ошибка в обработчике /start: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при обработке команды.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    help_text = (
        "📚 Справка:\n\n"
        "• Для анализа, мониторинга и сервиса используйте кнопки снизу.\n"
        "• Для ручной сделки нажмите «Купить» или «Продать» и введите символ с объёмом.\n"
        "• Автоторговля и мониторинг также включаются кнопками.\n\n"
        "⚠️ Торговля сопряжена с риском. Используйте бота ответственно."
    )
    await _reply_to_all(update, help_text, reply_markup=_get_command_keyboard())


async def get_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    balance = bybit_service.get_balance()
    if balance is not None:
        await _reply_to_all(update, f"💰 Баланс: {balance} USDT")
    else:
        await _reply_to_all(update, "❌ Не удалось получить баланс. Проверьте API ключи.")


async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /price"""
    logger.info(f"✅✅✅ КОМАНДА /price ОБРАБОТАНА! От {update.effective_user.id}, args: {context.args}")
    chat_id = update.effective_chat.id
    logger.info(f"Chat ID: {chat_id}, Разрешенные: {ALLOWED_CHAT_IDS}")
    if not check_access(chat_id):
        logger.warning(f"Доступ запрещен для chat_id: {chat_id}")
        await update.message.reply_text(f"❌ Доступ запрещен. Ваш Chat ID: {chat_id}")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите символ. Пример: /price BTCUSDT")
        return
    
    symbol = context.args[0].upper()
    logger.info(f"Запрос цены для символа: {symbol}")
    ticker = bybit_service.get_ticker(symbol)
    logger.info(f"Результат get_ticker: {ticker}")
    
    if ticker:
        logger.info(f"Отправка данных о цене для {symbol}")
        message = f"""
📊 {ticker['symbol']}

💰 Цена: ${ticker['last_price']}
📈 Изменение 24ч: {float(ticker['change_24h']) * 100:.2f}%
📊 Объем 24ч: {ticker['volume_24h']}
🔵 Bid: ${ticker['bid_price']}
🔴 Ask: ${ticker['ask_price']}
        """
        logger.info(f"Сообщение с ценой сформировано, отправка...")
        await update.message.reply_text(message)
        logger.info(f"Сообщение отправлено успешно")
    else:
        logger.warning(f"get_ticker вернул None для {symbol}")
        await update.message.reply_text(f"❌ Не удалось получить данные для {symbol}")


async def analyze_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /analyze - детальный анализ фьючерсного рынка"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите символ. Пример: /analyze BTCUSDT")
        return
    
    symbol = context.args[0].upper()
    
    # Отправляем сообщение о загрузке
    loading_msg = await update.message.reply_text("🤖 Собираю данные и анализирую рынок с помощью AI...")
    
    try:
        # Получаем комплексные данные о рынке
        market_data = bybit_service.get_market_data_comprehensive(symbol)
        historical_snapshot = market_analysis_service.get_historical_data(symbol)
        if market_data is not None:
            market_data["historical"] = historical_snapshot
        
        if not market_data or not market_data.get('ticker'):
            await loading_msg.delete()
            await update.message.reply_text(f"❌ Не удалось получить данные для {symbol}")
            return
        
        ticker = market_data['ticker']
        
        # Получаем детальный анализ от AI
        analysis = ai_service.analyze_market(market_data, db_service=db_service)
        
        # Формируем краткую сводку перед детальным анализом
        funding = market_data.get('funding', {})
        oi = market_data.get('open_interest', {})
        position = market_data.get('current_position')
        
        summary = f"""
📊 {symbol} - Краткая сводка

💰 Цена: ${ticker['last_price']}
📈 Изменение 24ч: {float(ticker['change_24h']) * 100:.2f}%
📊 Объем 24ч: {ticker['volume_24h']}
🔵 Bid: ${ticker['bid_price']} | 🔴 Ask: ${ticker['ask_price']}

💹 Funding Rate: {funding.get('funding_rate', 'N/A') if funding else 'N/A'}
📊 Open Interest: {oi.get('open_interest', 'N/A') if oi else 'N/A'}
💼 Позиция: {f"{position.get('side')} {position.get('size')} (P&L: {position.get('unrealised_pnl')})" if position else "Нет позиции"}
💵 Баланс: {market_data.get('balance', '0')} USDT
"""
        if historical_snapshot:
            supports_values = historical_snapshot.get("support_levels", [])
            resistances_values = historical_snapshot.get("resistance_levels", [])
            supports = ", ".join(f"${v:.2f}" for v in supports_values[:3]) if supports_values else "нет"
            resistances = ", ".join(f"${v:.2f}" for v in resistances_values[:3]) if resistances_values else "нет"
            smart_money = historical_snapshot.get("smart_money") or {}
            smart_bias_ru = _translate_signal_value(historical_snapshot.get("smart_money_bias"))
            ema_signal_ru = _translate_signal_value(historical_snapshot.get('ema_signal'))
            summary += (
                f"\n🕒 Исторический анализ ({historical_snapshot.get('analysis_window', 'N/A')}): "
                f"{historical_snapshot.get('historical_trend', historical_snapshot.get('price_structure', 'нет данных'))}\n"
                f"📍 Поддержки: {supports}\n"
                f"📍 Сопротивления: {resistances}\n"
                f"📊 Свечной комментарий: {historical_snapshot.get('price_structure', 'нет данных')}\n"
                f"📶 EMA(50/200): {historical_snapshot.get('ema_50', 'N/A')} / {historical_snapshot.get('ema_200', 'N/A')} "
                f"(сигнал: {ema_signal_ru})\n"
                f"💠 VWAP: {historical_snapshot.get('vwap', 'N/A')} (Δ {historical_snapshot.get('vwap_distance', 0):.2f}%)"
            )
            summary += (
                f"\n🐋 Крупные игроки: {smart_bias_ru} "
                f"(нетто {smart_money.get('net_flow', 0):,.0f}$)"
            )

        summary += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await loading_msg.delete()
        
        # Отправляем краткую сводку
        await update.message.reply_text(summary)
        
        # Отправляем детальный анализ (может быть длинным, разбиваем если нужно)
        if len(analysis) > 4000:
            # Разбиваем на части
            parts = [analysis[i:i+4000] for i in range(0, len(analysis), 4000)]
            for i, part in enumerate(parts):
                await update.message.reply_text(f"🤖 Детальный анализ (часть {i+1}/{len(parts)}):\n\n{part}")
        else:
            await update.message.reply_text(f"🤖 Детальный анализ:\n\n{analysis}")
            
    except Exception as e:
        logger.error(f"Ошибка в analyze_market: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")


async def get_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /positions"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    positions = bybit_service.get_positions()
    
    if not positions:
        await update.message.reply_text("📭 Нет открытых позиций")
        return
    
    message = "📊 Открытые позиции:\n\n"
    active_found = False
    for pos in positions:
        # Пробуем разные варианты получения размера
        size = pos.get("size") or pos.get("qty") or pos.get("positionSize") or "0"
        try:
            size_float = float(size) if size and str(size) != "N/A" else 0
        except (ValueError, TypeError):
            size_float = 0
        
        if abs(size_float) > 0.0001:  # Более мягкое условие
            active_found = True
            raw_side = (pos.get("side") or "").strip().lower()
            if raw_side == "buy":
                display_side = "ЛОНГ"
            elif raw_side == "sell":
                display_side = "ШОРТ"
            else:
                display_side = "ЛОНГ" if size_float > 0 else "ШОРТ"
            stop_loss = pos.get("stopLoss") or pos.get("slPrice") or "—"
            take_profit = pos.get("takeProfit") or pos.get("tpPrice") or "—"
            message += f"""
🔹 {pos.get('symbol', 'N/A')} ({display_side})
Размер: {abs(size_float):.6f}
Цена входа: ${pos.get('avgPrice', 'N/A')}
Текущая цена: ${pos.get('markPrice', 'N/A')}
P&L: ${pos.get('unrealisedPnl', 'N/A')}
Плечо: {pos.get('leverage', 'N/A')}x
SL: {stop_loss} | TP: {take_profit}
---
            """
    
    if not active_found:
        await update.message.reply_text("📭 Нет активных позиций (все позиции имеют размер 0)")
        return
    
    message += "\n💡 Закрыть все: /close_all\n💡 Обновить TP/SL: /update_tp_sl"
    await update.message.reply_text(message)


async def get_trading_decisions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /decisions - получение торговых решений (аналог nof1.ai)"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    # Отправляем сообщение о загрузке
    loading_msg = await update.message.reply_text("🤖 Анализирую позиции и генерирую торговые решения...")
    
    try:
        # Получаем торговые решения
        result = trading_decision_service.generate_trading_decisions()
        
        if not result:
            await loading_msg.delete()
            await update.message.reply_text("❌ Не удалось получить торговые решения")
            return
        
        available_capital = result.get("available_capital", 0)
        nav = result.get("nav", 0)
        current_prices = result.get("current_prices", {})
        positions = result.get("positions", [])
        decisions = result.get("decisions", [])
        
        # Формируем сводку
        summary = f"""
📊 TRADING DECISIONS REPORT

💰 Available Capital: {available_capital:.2f} USDT
📈 Current NAV: {nav:.2f} USDT

📊 Current Prices:
"""
        for symbol, price in current_prices.items():
            summary += f"  {symbol}: ${price}\n"
        
        summary += f"\n📋 Open Positions: {len(positions)}\n"
        
        await loading_msg.delete()
        await update.message.reply_text(summary)
        
        # Отправляем решения для каждой позиции
        if not decisions:
            await update.message.reply_text("⚠️ Нет торговых решений для текущих позиций")
            return
        
        for decision in decisions:
            signal = decision.get("signal", "hold").upper()
            symbol = decision.get("symbol", "N/A")
            justification = decision.get("justification", "N/A")
            confidence = decision.get("confidence", 0.0)
            risk_usd = decision.get("risk_usd", 0.0)
            stop_loss = decision.get("stop_loss", "N/A")
            profit_target = decision.get("profit_target", "N/A")
            invalidation = decision.get("invalidation_condition", "N/A")
            quantity = decision.get("quantity", 0)
            leverage = decision.get("leverage", "N/A")
            is_add = decision.get("is_add", False)
            
            decision_msg = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 {symbol}

SIGNAL: {signal}
IS ADD: {is_add}
CONFIDENCE: {confidence:.2f}
RISK USD: {risk_usd:.2f}

QUANTITY: {quantity}
LEVERAGE: {leverage}x
STOP LOSS: {stop_loss}
PROFIT TARGET: {profit_target}

INVALIDATION CONDITION:
{invalidation}

JUSTIFICATION:
{justification}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            """
            
            # Разбиваем длинные сообщения
            if len(decision_msg) > 4000:
                parts = [decision_msg[i:i+4000] for i in range(0, len(decision_msg), 4000)]
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(decision_msg)
        
        # Отправляем JSON формат (для программистов)
        import json
        json_output = json.dumps(decisions, indent=2, ensure_ascii=False)
        if len(json_output) > 4000:
            parts = [json_output[i:i+4000] for i in range(0, len(json_output), 4000)]
            await update.message.reply_text("📄 JSON формат:")
            for part in parts:
                await update.message.reply_text(f"```json\n{part}\n```")
        else:
            await update.message.reply_text(f"📄 JSON формат:\n```json\n{json_output}\n```")
            
    except Exception as e:
        logger.error(f"Ошибка в get_trading_decisions: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при генерации решений: {str(e)}")


async def get_opportunities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /opportunities - глубокий анализ популярных монет без покупки"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    # Отправляем сообщение о загрузке
    loading_msg = await update.message.reply_text(
        "🔍 Провожу глубокий анализ популярных криптовалют...\n"
        "📊 Анализирую волатильность, ликвидность, funding rates...\n"
        "⚙️ Рассчитываю адаптивное безопасное плечо...\n"
        "⏳ Это может занять 30-60 секунд..."
    )
    
    try:
        # Получаем анализ всех популярных монет
        results = market_analysis_service.analyze_all_coins()
        
        if not results:
            await loading_msg.delete()
            await update.message.reply_text("❌ Не удалось получить анализ")
            return
        
        await loading_msg.delete()
        
        # Отправляем общую сводку
        summary = f"""
📊 ГЛУБОКИЙ АНАЛИЗ РЫНКА КРИПТОВАЛЮТ

💰 Ваш капитал: ${market_analysis_service.capital}
🎯 Цель в день: ${market_analysis_service.daily_target} (5-10$)
🛡️ Максимальный риск: {market_analysis_service.max_daily_risk*100}% ({market_analysis_service.max_daily_risk * market_analysis_service.capital}$)

📈 Проанализировано монет: {len(results)}
⏰ Период анализа: 24 часа + текущие метрики

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
        
        await update.message.reply_text(summary)
        
        # Отправляем топ-3 лучшие возможности
        top_3 = results[:3]
        
        for i, coin_data in enumerate(top_3, 1):
            symbol = coin_data["symbol"]
            data = coin_data["data"]
            leverage_info = coin_data["leverage_info"]
            position_info = coin_data["position_info"]
            recommendation = coin_data["recommendation"]
            score = coin_data["score"]
            
            message = f"""
🏆 ТОП {i}: {symbol} (Score: {score:.1f}/100)

📊 ТЕКУЩИЕ ДАННЫЕ:
💰 Цена: ${data['current_price']}
📈 Изменение 24ч: {data['change_24h']:.2f}%
📊 Объем сделок 24ч: {market_analysis_service._format_volume_value(data.get('volume_24h', 0))}
💹 Funding Rate: {data['funding_rate']*100:.4f}%
📊 Open Interest: {data['open_interest']}
📉 Волатильность: {data['volatility']}%
💧 Ликвидность: {data['liquidity_score']}/10

⚙️ АДАПТИВНОЕ ПЛЕЧО:
🔧 Рекомендуемое: {leverage_info['recommended_leverage']}x
🛡️ Максимально безопасное: {leverage_info['max_safe_leverage']}x
📊 Категория волатильности: {leverage_info['volatility_category']}
⚠️ Уровень риска: {leverage_info['risk_level']}

💼 РЕКОМЕНДУЕМАЯ ПОЗИЦИЯ:
📦 Размер: {position_info.get('position_size', 0):.8f}
💰 Цена входа: ${position_info.get('entry_price', 0):.2f}
🛑 Стоп-лосс: ${position_info.get('stop_loss', 0):.2f}
🎯 Тейк-профит: ${position_info.get('take_profit', 0):.2f}
⚖️ Risk-Reward: 1:{position_info.get('risk_reward_ratio', 0):.2f}
💵 Риск: ${position_info.get('risk_amount', 0):.2f}
💰 Потенциальная прибыль: ${position_info.get('potential_profit', 0):.2f}
📊 Объем позиции: ${position_info.get('notional', 0):.2f}

{recommendation}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            """
            
            if len(message) > 4000:
                parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
                for part in parts:
                    await update.message.reply_text(part)
            else:
                await update.message.reply_text(message)
        
        # Отправляем остальные монеты кратко
        if len(results) > 3:
            other_coins = results[3:]
            other_msg = "\n📋 ОСТАЛЬНЫЕ МОНЕТЫ:\n\n"
            
            for coin_data in other_coins:
                symbol = coin_data["symbol"]
                score = coin_data["score"]
                leverage = coin_data["leverage_info"]["recommended_leverage"]
                risk = coin_data["leverage_info"]["risk_level"]
                profit = coin_data["position_info"].get("potential_profit", 0)
                
                other_msg += f"{symbol}: Score {score:.1f} | Leverage {leverage}x | Риск {risk} | Прибыль ${profit:.2f}\n"
            
            await update.message.reply_text(other_msg)
        
        # Итоговая рекомендация
        best_coin = results[0]
        final_recommendation = f"""
🎯 ИТОГОВАЯ РЕКОМЕНДАЦИЯ:

🏆 ЛУЧШАЯ ВОЗМОЖНОСТЬ: {best_coin['symbol']}
📊 Score: {best_coin['score']:.1f}/100
⚙️ Leverage: {best_coin['leverage_info']['recommended_leverage']}x
💰 Потенциальная прибыль: ${best_coin['position_info'].get('potential_profit', 0):.2f}
⚠️ Уровень риска: {best_coin['leverage_info']['risk_level']}

⚠️ ВАЖНО: Это только анализ и рекомендации!
❌ Покупка НЕ выполняется автоматически
✅ Используйте команду /buy {best_coin['symbol']} 2% для безопасной покупки

🛡️ Все сделки защищены стоп-лоссами и тейк-профитами
        """
        
        await update.message.reply_text(final_recommendation)
        
    except Exception as e:
        logger.error(f"Ошибка в get_opportunities: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")


async def get_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /news - новостной фон и эмоциональный анализ"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if not news_service:
        await update.message.reply_text("❌ Новостной сервис недоступен. Проверьте PERPLEXITY_API_KEY")
        return
    
    symbol = "BTC"  # По умолчанию
    if context.args:
        symbol = context.args[0].upper().replace("USDT", "")
    
    # Отправляем сообщение о загрузке
    loading_msg = await update.message.reply_text(f"📰 Собираю новости и анализирую эмоциональный фон для {symbol}...")
    
    try:
        # Получаем новостной контекст
        news_context = news_service.get_trading_news_context(symbol)
        
        await loading_msg.delete()
        
        # Формируем сообщение
        message = f"""
📰 НОВОСТНОЙ ФОН И ЭМОЦИОНАЛЬНЫЙ АНАЛИЗ

💰 Символ: {symbol}

📊 НАСТРОЕНИЕ:
🎯 По активу: {news_context.get('symbol_sentiment', 'N/A')}
🌐 Общий рынок: {news_context.get('market_sentiment', 'N/A')}

💡 РЕКОМЕНДАЦИЯ:
{news_context.get('recommendation', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 КЛЮЧЕВЫЕ НОВОСТИ ПО АКТИВУ:
        """
        
        symbol_news = news_context.get('symbol_news', [])
        if symbol_news:
            for i, news in enumerate(symbol_news[:3], 1):
                message += f"\n{i}. {news.get('title', 'Без заголовка')}\n"
                if news.get('snippet'):
                    message += f"   {news['snippet'][:150]}...\n"
                message += f"   🔗 {news.get('url', '')}\n"
        else:
            message += "\nНовости не найдены\n"
        
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "\n🌐 ОБЩИЙ РЫНОЧНЫЙ ФОН:\n"
        
        market_news = news_context.get('market_news', [])
        if market_news:
            for i, news in enumerate(market_news[:3], 1):
                message += f"\n{i}. {news.get('title', 'Без заголовка')}\n"
                if news.get('snippet'):
                    message += f"   {news['snippet'][:150]}...\n"
        else:
            message += "\nНовости не найдены\n"
        
        # Разбиваем длинные сообщения
        if len(message) > 4000:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Ошибка в get_news: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при получении новостей: {str(e)}")


async def get_market_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /market_sentiment - общий эмоциональный фон рынка"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if not news_service:
        await update.message.reply_text("❌ Новостной сервис недоступен. Проверьте PERPLEXITY_API_KEY")
        return
    
    # Отправляем сообщение о загрузке
    loading_msg = await update.message.reply_text("🌐 Анализирую общий эмоциональный фон крипто-рынка...")
    
    try:
        # Получаем общий фон рынка
        market_sentiment = news_service.get_market_sentiment()
        
        await loading_msg.delete()
        
        sentiment = market_sentiment.get('sentiment', 'NEUTRAL')
        sentiment_emoji = {
            "BULLISH": "📈",
            "BEARISH": "📉",
            "NEUTRAL": "➡️"
        }
        emoji = sentiment_emoji.get(sentiment, "➡️")
        
        message = f"""
🌐 ОБЩИЙ ЭМОЦИОНАЛЬНЫЙ ФОН КРИПТО-РЫНКА

{emoji} Настроение: {sentiment}
📰 Проанализировано новостей: {market_sentiment.get('news_count', 0)}
⏰ Время анализа: {market_sentiment.get('timestamp', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 ТОП НОВОСТЕЙ РЫНКА:
        """
        
        news_list = market_sentiment.get('news', [])
        if news_list:
            for i, news in enumerate(news_list[:5], 1):
                message += f"\n{i}. {news.get('title', 'Без заголовка')}\n"
                if news.get('snippet'):
                    message += f"   {news['snippet'][:200]}...\n"
                message += f"   🔗 {news.get('url', '')}\n"
        else:
            message += "\nНовости не найдены\n"
        
        # Добавляем интерпретацию
        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if sentiment == "BULLISH":
            message += "\n✅ Бычий фон - рынок настроен позитивно\n"
            message += "💡 Рекомендация: Рассмотреть лонг позиции на сильных активах"
        elif sentiment == "BEARISH":
            message += "\n⚠️ Медвежий фон - рынок настроен негативно\n"
            message += "💡 Рекомендация: Осторожность, рассмотреть шорт или ожидание"
        else:
            message += "\n➡️ Нейтральный фон - смешанные сигналы\n"
            message += "💡 Рекомендация: Требуется дополнительный технический анализ"
        
        # Разбиваем длинные сообщения
        if len(message) > 4000:
            parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Ошибка в get_market_sentiment: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при анализе настроения: {str(e)}")


async def get_market_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /market_overview - объединенный анализ рынка и новостей"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return

    loading_msg = await update.message.reply_text(
        "📊 Собираю технические и новостные данные...\n"
        "⚙️ Анализирую волатильность, funding, ликвидность...\n"
        "📰 Сопоставляю с эмоциональным фоном рынка..."
    )

    try:
        analysis_results = market_analysis_service.analyze_all_coins()
        if not analysis_results:
            await loading_msg.delete()
            await update.message.reply_text("❌ Не удалось получить технический анализ")
            return

        market_sentiment = news_service.get_market_sentiment() if news_service else None
        overview = market_analysis_service.get_market_overview(analysis_results, market_sentiment)

        await loading_msg.delete()

        sentiment = market_sentiment.get("sentiment", "NEUTRAL") if market_sentiment else "N/A"
        sentiment_emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}
        emoji = sentiment_emoji.get(sentiment, "➡️")

        order_flow = overview.get("order_flow", {})
        message = f"""
📊 КОМБИНИРОВАННЫЙ ОБЗОР РЫНКА

{emoji} Эмоциональный фон: {sentiment}
⚖️ Средняя волатильность (топ-10): {overview.get('avg_volatility', 0)}%
💹 Средний funding: {overview.get('avg_funding', 0)}%
🔥 Перекуплено (покупок): {overview.get('overbought_count', 0)}
🧊 Перепродано (продаж): {overview.get('oversold_count', 0)}
📈 Заявок на покупку: {order_flow.get('long_orders', 0)}
📉 Заявок на продажу: {order_flow.get('short_orders', 0)}
📊 Тренд спроса/предложения: {order_flow.get('trend', 'сбалансирован')}
💰 Суммарный объём сделок (24ч): {market_analysis_service._format_volume_value(overview.get('total_volume', 0))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 ТОП ВОЗМОЖНОСТИ:
"""

        for i, coin in enumerate(overview.get("best_assets", [])[:3], 1):
            data = coin["data"]
            position = coin["position_info"]
            ema_signal_ru = _translate_signal_value(data.get('ema_signal'))
            smart_bias_ru = _translate_signal_value(data.get('smart_money_bias'))
            status_ru = _translate_status_value(data.get('overbought_status'))
            cooldown_remaining = _get_cooldown_remaining(coin["symbol"])
            cooldown_note = f"\n• ⏸ Пауза ещё {int(cooldown_remaining.total_seconds() // 60)} мин" if cooldown_remaining else ""
            # Рассчитываем процент прибыли и чистую прибыль с учетом комиссий
            entry_price = data['current_price']
            take_profit_price = position.get('take_profit', entry_price)
            stop_loss_price = position.get('stop_loss', entry_price)
            
            # Процент прибыли от входа до тейк-профита
            if entry_price > 0:
                pnl_percent = abs((take_profit_price - entry_price) / entry_price) * 100
                profit_calc = _calculate_net_profit(pnl_percent, use_maker=True, include_additional_fee=False)
                net_profit_percent = profit_calc['net_pnl']
                net_profit_usd = position.get('potential_profit', 0) * (net_profit_percent / pnl_percent) if pnl_percent > 0 else 0
            else:
                net_profit_percent = 0
                net_profit_usd = 0
            
            message += f"""
{i}. {coin['symbol']} | Score {coin['score']:.1f}
• Цена: ${data['current_price']}
• Изм. 24ч: {data['change_24h']:.2f}% | Волатильность: {data['volatility']}%
• Объём 24ч: {market_analysis_service._format_volume_value(data.get('volume_24h', 0))}
• Фандинг: {data['funding_rate']*100:.4f}% | Состояние: {status_ru}
• EMA(50/200): {ema_signal_ru} | Крупные игроки: {smart_bias_ru} (нетто {data.get('smart_money_flow', 0):,.0f}$)
• История: {data.get('historical_trend', data.get('price_structure', 'нет данных'))}
• Рекомендуемое плечо: {coin['leverage_info']['recommended_leverage']}x
• Потенциальная прибыль: ${position.get('potential_profit', 0):.2f} (брутто)
• 💰 Чистая прибыль: ${net_profit_usd:.2f} ({net_profit_percent:.2f}% с учетом комиссий мейкер 0.02% + тейкер 0.055%)
• План выхода: тейк ${position.get('take_profit', 0):.2f} / стоп ${position.get('stop_loss', 0):.2f}{cooldown_note}
"""

        if market_sentiment and market_sentiment.get("news"):
            message += "\n📰 Ключевые новости рынка (RU/EN):\n"
            for news in market_sentiment["news"][:3]:
                message += f"• {news.get('title', 'Без заголовка')}\n"

        await _send_long_message(update, message)

        # Автоматическая торговля: открываем только одну позицию (лучшую)
        trade_msg = await _execute_auto_trade(overview, update)
        if trade_msg:
            await update.message.reply_text(trade_msg)

    except Exception as e:
        logger.error(f"Ошибка в get_market_overview: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при комбинированном анализе: {str(e)}")


async def prediction_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /prediction_test - запуск скрипта теста предсказаний."""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return

    loading_msg = await update.message.reply_text(
        "🧪 Запускаю тест предсказаний...\n"
        "⚙️ Анализирую топ монеты, адаптивное плечо, эмоциональный фон..."
    )

    try:
        analysis_results = market_analysis_service.analyze_all_coins()
        if not analysis_results:
            await loading_msg.delete()
            await update.message.reply_text("❌ Не удалось получить технический анализ (проверьте API Bybit).")
            return

        market_sentiment = news_service.get_market_sentiment() if news_service else None
        overview = market_analysis_service.get_market_overview(analysis_results, market_sentiment)

        await loading_msg.delete()

        order_flow = overview.get("order_flow", {})
        summary = {
            "Средняя волатильность": f"{overview.get('avg_volatility')}%",
            "Средний funding": f"{overview.get('avg_funding')}%",
            "Перекуплено (покупок)": overview.get("overbought_count"),
            "Перепродано (продаж)": overview.get("oversold_count"),
            "Заявок на покупку": order_flow.get("long_orders", 0),
            "Заявок на продажу": order_flow.get("short_orders", 0),
            "Спрос/предложение": order_flow.get("trend", "сбалансирован"),
            "Общий sentiment": market_sentiment.get("sentiment") if market_sentiment else "N/A",
            "Суммарный объём (24ч)": market_analysis_service._format_volume_value(overview.get("total_volume", 0))
        }

        summary_msg = "📊 Результат теста предсказаний:\n"
        for key, val in summary.items():
            summary_msg += f"{key}: {val}\n"
        await update.message.reply_text(summary_msg)

        # Отправляем топ возможности
        best_assets = overview.get("best_assets", [])[:3]
        if best_assets:
            details = "🏆 ТОП возможностей:\n"
            for idx, asset in enumerate(best_assets, 1):
                data = asset["data"]
                pos = asset["position_info"]
                ema_signal_ru = _translate_signal_value(data.get('ema_signal'))
                smart_bias_ru = _translate_signal_value(data.get('smart_money_bias'))
                status_ru = _translate_status_value(data.get('overbought_status'))
                cooldown_remaining = _get_cooldown_remaining(asset["symbol"])
                cooldown_note = f"\n   ⏸ Пауза ещё {int(cooldown_remaining.total_seconds() // 60)} мин" if cooldown_remaining else ""
                
                # Рассчитываем чистую прибыль с учетом комиссий
                entry_price = data['current_price']
                take_profit_price = pos.get('take_profit', entry_price)
                if entry_price > 0:
                    pnl_percent = abs((take_profit_price - entry_price) / entry_price) * 100
                    profit_calc = _calculate_net_profit(pnl_percent, use_maker=True, include_additional_fee=False)
                    net_profit_percent = profit_calc['net_pnl']
                    net_profit_usd = pos.get('potential_profit', 0) * (net_profit_percent / pnl_percent) if pnl_percent > 0 else 0
                else:
                    net_profit_percent = 0
                    net_profit_usd = 0
                
                details += (
                    f"\n{idx}. {asset['symbol']} (Score {asset['score']:.1f})\n"
                    f"   Цена: ${data['current_price']} | Δ24ч: {data['change_24h']:.2f}%\n"
                    f"   Волатильность: {data['volatility']}% | Фандинг: {data['funding_rate']*100:.4f}%\n"
                    f"   Объём 24ч: {market_analysis_service._format_volume_value(data.get('volume_24h', 0))}\n"
                    f"   Состояние: {status_ru} | EMA: {ema_signal_ru}\n"
                    f"   Крупные игроки: {smart_bias_ru} (нетто {data.get('smart_money_flow', 0):,.0f}$)\n"
                    f"   Рекомендуемое плечо: {asset['leverage_info']['recommended_leverage']}x\n"
                    f"   Потенциальная прибыль: ${pos.get('potential_profit', 0):.2f} (брутто)\n"
                    f"   💰 Чистая прибыль: ${net_profit_usd:.2f} ({net_profit_percent:.2f}% с учетом комиссий)\n"
                    f"   План выхода: тейк ${pos.get('take_profit', 0):.2f} / стоп ${pos.get('stop_loss', 0):.2f}{cooldown_note}\n"
                )
            await update.message.reply_text(details)

        if market_sentiment and market_sentiment.get("news"):
            news_msg = "📰 Ключевые новости рынка:\n"
            for news in market_sentiment["news"][:3]:
                news_msg += f"• {news.get('title', 'Без заголовка')}\n"
            await update.message.reply_text(news_msg)

        await update.message.reply_text(
            "✅ Тест завершён. Используйте /buy SYMBOL 2% для безопасного входа."
        )

    except Exception as e:
        logger.error(f"Ошибка в prediction_test: {e}", exc_info=True)
        await loading_msg.delete()
        await update.message.reply_text(f"❌ Ошибка при тесте предсказаний: {str(e)}")


async def _execute_auto_trade(overview: Dict, update: Update) -> Optional[str]:
    """
    Выполнить автоматическую торговую сделку в рамках /market_overview.
    Теперь заполняем столько доступных слотов, сколько разрешает MAX_ACTIVE_POSITIONS.
    """
    try:
        global LIMIT_NOTIFICATION_SENT, db_service
        
        existing_positions = bybit_service.get_positions() or []
        active_positions = [pos for pos in existing_positions if _is_position_active(pos)]
        active_count = len(active_positions)
        
        # Если позиций меньше лимита - сбрасываем флаг уведомления
        if active_count < MAX_ACTIVE_POSITIONS:
            LIMIT_NOTIFICATION_SENT = False
        
        if active_count >= MAX_ACTIVE_POSITIONS:
            active_symbols = [pos.get("symbol") for pos in active_positions]
            logger.info(
                f"Активных позиций {active_count}/{MAX_ACTIVE_POSITIONS}: {active_symbols}. "
                "Лимит достигнут, новую сделку не открываем."
            )
            # Отправляем уведомление только один раз при первом достижении лимита
            if not LIMIT_NOTIFICATION_SENT:
                LIMIT_NOTIFICATION_SENT = True
                return (
                    f"⏸ Достигнут лимит в {MAX_ACTIVE_POSITIONS} активных сделок.\n"
                    "Закройте позиции или дождитесь завершения, прежде чем открывать новые."
                )
            # Если уведомление уже было отправлено - просто возвращаем None (не спамим)
            return None
        
        best_assets = overview.get("best_assets", [])
        if not best_assets:
            return None

        eligible_assets: List[Dict] = []
        blocked_assets: List[str] = []
        for asset in best_assets:
            symbol = asset["symbol"].upper()
            block_reason = _check_symbol_quarantine(symbol, existing_positions)
            if block_reason:
                blocked_assets.append(f"• {symbol}: {block_reason}")
                continue
            eligible_assets.append(asset)
        
        if not eligible_assets:
            if blocked_assets:
                await update.message.reply_text(
                    "⏸ Все топ-монеты в паузе или уже заняты:\n"
                    + "\n".join(blocked_assets)
                    + "\nПопробую снова при следующем запуске."
                )
            return None
        
        slots_available = MAX_ACTIVE_POSITIONS - active_count
        slots_to_fill = min(slots_available, len(eligible_assets))
        if slots_to_fill <= 0:
            return None

        ai_recommended_symbol = None
        ai_analysis = None
        
        # Ограничиваем количество монет для AI анализа, чтобы ускорить процесс
        analysis_pool = eligible_assets[:5]  # Уменьшено с 10 до 5 для ускорения
        ai_market_data = []
        ai_trade_plans: Dict[str, Dict] = {}
        market_payloads: Dict[str, Dict] = {}
        if analysis_pool:
            for asset in analysis_pool:
                symbol = asset["symbol"]
                market_data = bybit_service.get_market_data_comprehensive(symbol)
                if not market_data:
                    continue
                
                historical = market_analysis_service.get_historical_data(symbol)
                if historical:
                    market_data["historical"] = historical
                
                order_book = bybit_service.get_order_book(symbol, limit=50)
                if order_book:
                    market_data["order_book"] = order_book
                
                if news_service:
                    symbol_news = news_service.get_symbol_specific_news(symbol, max_results=5)
                    if symbol_news:
                        news_summary = []
                        for news_item in symbol_news.get("news", [])[:5]:
                            title = news_item.get("title", "Без заголовка")
                            snippet = news_item.get("snippet", "")
                            url = news_item.get("url", "")
                            source = news_item.get("source", "")
                            published = news_item.get("published_at", "")
                            piece = f"• {title}"
                            if source:
                                piece += f" ({source})"
                            if published:
                                piece += f" — {published}"
                            if snippet:
                                piece += f"\n  {snippet.strip()}"
                            if url:
                                piece += f"\n  🔗 {url}"
                            news_summary.append(piece)
                        market_data["news"] = {
                            "sentiment": symbol_news.get("sentiment", "NEUTRAL"),
                            "summary": symbol_news.get("summary", ""),
                            "news_items": "\n".join(news_summary) if news_summary else "Нет новостей"
                        }
                
                payload = {
                    "symbol": symbol,
                    "market_data": market_data,
                    "score": asset["score"],
                    "data": asset["data"]
                }
                ai_market_data.append(payload)
                market_payloads[symbol] = payload
            
            if ai_market_data:
                try:
                    # Получаем баланс для контекста
                    balance = bybit_service.get_balance()
                    # Передаем существующие позиции, баланс и db_service в AI для учета корреляции и контекста
                    logger.info(f"🔍 Вызываю AI analyze_market_for_trade_selection с db_service={'✅ доступен' if db_service else '❌ None'}")
                    logger.info(f"🔍 db_service type: {type(db_service)}, connection: {'✅' if db_service and hasattr(db_service, 'connection') and db_service.connection else '❌'}")
                    ai_analysis = ai_service.analyze_market_for_trade_selection(ai_market_data, existing_positions, balance, db_service)
                    if ai_analysis and ai_analysis.get("recommended_symbol"):
                        ai_recommended_symbol = ai_analysis.get("recommended_symbol")
                        logger.info(f"AI рекомендует: {ai_recommended_symbol}")
                except Exception as e:
                    logger.warning(f"Ошибка при AI-анализе для выбора монеты: {e}")
                
                for payload in ai_market_data:
                    symbol = payload["symbol"]
                    try:
                        logger.debug(f"Вызываю AI analyze_asset_trade_plan для {symbol} с db_service={'✅' if db_service else '❌ None'}")
                        plan = ai_service.analyze_asset_trade_plan(payload, db_service)
                        if plan and plan.get("entry_price") and plan.get("stop_loss") and plan.get("take_profit"):
                            ai_trade_plans[symbol] = plan
                            logger.info(f"AI-план подготовлен для {symbol}")
                    except Exception as plan_error:
                        logger.warning(f"AI не смог построить план для {symbol}: {plan_error}")

        opened_messages: List[str] = []
        used_symbols: set[str] = set()

        def pick_next_asset() -> Tuple[Optional[Dict], Optional[Dict]]:
            if ai_recommended_symbol:
                asset = next(
                    (a for a in eligible_assets if a["symbol"] == ai_recommended_symbol and a["symbol"] not in used_symbols),
                    None
                )
                if asset:
                    return asset, ai_trade_plans.get(asset["symbol"])
            for asset in eligible_assets:
                if asset["symbol"] not in used_symbols:
                    return asset, ai_trade_plans.get(asset["symbol"])
            return None, None

        for _ in range(slots_to_fill):
            asset, asset_ai_plan = pick_next_asset()
            if not asset:
                break
            used_symbols.add(asset["symbol"])
            recommend_context = ai_analysis if asset.get("symbol") == ai_recommended_symbol else None
            trade_msg = await _open_trade_for_asset(asset, overview, update, asset_ai_plan, recommend_context)
            if trade_msg:
                opened_messages.append(trade_msg)
        
        if opened_messages:
            return "\n".join(opened_messages)
        return None

    except Exception as e:
        logger.error(f"Ошибка при авто-тест сделке: {e}", exc_info=True)
        return f"⚠️ Тестовая сделка не выполнена: {str(e)}"


async def _open_trade_for_asset(asset: Dict, overview: Dict, update: Update, ai_plan: Optional[Dict], ai_recommendation: Optional[Dict]) -> Optional[str]:
    """Разместить сделку по конкретному asset из best_assets."""
    symbol = asset["symbol"]
    data = asset["data"]
    leverage = asset["leverage_info"]["recommended_leverage"]
    order_flow = overview.get("order_flow", {}) or {}
    # Получаем текущие позиции один раз, чтобы использовать их во всех проверках
    existing_positions = bybit_service.get_positions() or []
    
    # Проверка дневного лимита убытков (учитывает unrealized PnL)
    balance = bybit_service.get_balance()
    current_pnl = 0.0  # Realized PnL за день
    daily_loss_check = risk_management_service.check_daily_loss_limit(
        balance, 
        current_pnl, 
        positions=existing_positions
    )
    if daily_loss_check.get("is_limit_reached"):
        unrealized = daily_loss_check.get("unrealized_loss", 0)
        realized = daily_loss_check.get("realized_loss", 0)
        logger.warning(f"Дневной лимит убытков достигнут: {daily_loss_check.get('daily_loss_percent', 0):.2f}% (realized: {realized:.2f}, unrealized: {unrealized:.2f})")
        return f"⚠️ Дневной лимит убытков достигнут ({daily_loss_check.get('daily_loss_percent', 0):.2f}%). Торговля приостановлена."
    
    entry_price = data["current_price"]
    ai_note = ""
    missing_data_note = ""
    
    # Получаем ATR из исторических данных
    historical = data.get("historical") or {}
    atr = historical.get("atr")

    # Определяем направление позиции заранее для проверки корреляции
    if ai_plan:
        plan_side = ai_plan.get("recommended_side", "Long")
        # Правильно определяем направление: учитываем и "Long"/"Short", и "Buy"/"Sell"
        plan_side_lower = str(plan_side).lower()
        if plan_side_lower in ["long", "buy"]:
            side = "Long"
        elif plan_side_lower in ["short", "sell"]:
            side = "Short"
        else:
            # Фолбэк на Long, если непонятное значение
            side = "Long"
            logger.warning(f"Неизвестное направление от AI: {plan_side}, используем Long по умолчанию")
    else:
        side = _determine_trade_side(data.get("overbought_status"), order_flow.get("trend"))
    
    # Проверка корреляции с существующими позициями (теперь с учетом направления)
    correlation_check = risk_management_service.check_correlation(symbol, existing_positions, new_side=side)
    if not correlation_check.get("is_safe"):
        warnings = correlation_check.get("warnings", [])
        logger.warning(f"Высокая корреляция для {symbol}: {warnings}")
        return f"⚠️ Высокая корреляция с существующими позициями. {', '.join(warnings)}"
    
    # Продолжаем с расчетом параметров сделки
    if ai_plan:
        ai_entry_price = ai_plan.get("entry_price")
        ai_stop_loss = ai_plan.get("stop_loss")
        ai_take_profit = ai_plan.get("take_profit")
        if ai_entry_price and ai_entry_price > 0:
            entry_price = ai_entry_price
        volatility_percent = max(data.get("volatility", 2) / 100, 0.01)
        if ai_stop_loss and ai_stop_loss > 0:
            stop_loss = ai_stop_loss
        else:
            stop_loss = risk_management_service.get_recommended_stop_loss(entry_price, side, volatility_percent, atr)
        if ai_take_profit and ai_take_profit > 0:
            take_profit = ai_take_profit
        else:
            target_gross_pnl = 0.5
            take_profit = entry_price * (1 + target_gross_pnl / 100) if side == "Long" else entry_price * (1 - target_gross_pnl / 100)
    else:
        volatility_percent = max(data.get("volatility", 2) / 100, 0.01)
        stop_loss = risk_management_service.get_recommended_stop_loss(entry_price, side, volatility_percent, atr)
        target_gross_pnl = 0.5
        take_profit = entry_price * (1 + target_gross_pnl / 100) if side == "Long" else entry_price * (1 - target_gross_pnl / 100)

    risk_amount = market_analysis_service.capital * market_analysis_service.max_daily_risk
    qty = risk_management_service.calculate_position_size(entry_price, stop_loss, risk_amount, leverage)
    qty = _normalize_order_qty(symbol, qty)
    if qty <= 0:
        return None

    order_side = "Buy" if side == "Long" else "Sell"
    logger.info(f"Попытка разместить ордер: {symbol}, side={order_side}, qty={qty}, entry={entry_price}, SL={stop_loss}, TP={take_profit}")
    order_result = bybit_service.place_order(
        symbol=symbol,
        side=order_side,
        qty=qty,
        stop_loss=stop_loss,
        take_profit=take_profit,
        prefer_maker=False
    )

    if not order_result or order_result.get("error"):
        error_text = order_result.get("error") if isinstance(order_result, dict) else "Bybit вернул ошибку."
        return f"⚠️ Не удалось разместить сделку ({error_text})."

    logger.info(f"✅ Ордер успешно размещен для {symbol}: {order_result}")
    # Карантин устанавливается при ЗАКРЫТИИ позиции, а не при открытии
    
    # Сохраняем сделку в БД
    if db_service:
        try:
            bot_name = getattr(config, "BOT_NAME", "main")
            db_service.save_trade(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                quantity=qty,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                bot_name=bot_name,
                status="open"
            )
            logger.info(f"💾 Сделка сохранена в БД: {symbol} {side}")
        except Exception as e:
            logger.warning(f"Не удалось сохранить сделку в БД: {e}")
    
    # Всегда планируем отложенное обновление TP/SL через TP_SL_REFRESH_DELAY_SECONDS,
    # даже если биржа сообщила, что уровни уже установлены. Так мы гарантируем,
    # что через ~30 секунд стоп/тейк будут пересчитаны и установлены повторно.
    logger.info(f"Планирую отложенное обновление TP/SL для {symbol} через {TP_SL_REFRESH_DELAY_SECONDS} сек.")
    _schedule_tp_sl_refresh(symbol)

    if side == "Long":
        pnl_percent = ((take_profit - entry_price) / entry_price) * 100 if entry_price > 0 else 0
    else:
        pnl_percent = ((entry_price - take_profit) / entry_price) * 100 if entry_price > 0 else 0
    profit_calc = _calculate_net_profit(pnl_percent, use_maker=True, include_additional_fee=False)
    net_profit_percent = profit_calc['net_pnl']

    explanation_source = ai_plan or ai_recommendation
    if explanation_source:
        confidence = explanation_source.get("confidence", 0)
        reasoning = explanation_source.get("reasoning", "")
        missing_data = explanation_source.get("missing_data", [])
        ai_note = f"\n🤖 AI-решение: уверенность {confidence*100:.0f}%\n💡 {reasoning}\n"
        if missing_data:
            missing_list = "\n".join([f"  • {item}" for item in missing_data])
            missing_data_note = f"\n⚠️ AI сообщает, что для 100% уверенности не хватает:\n{missing_list}\n"

    return (
        f"✅ Автоматическая сделка выполнена:\n\n"
        f"Монета: {symbol}\n"
        f"Тип: {'ЛОНГ' if side == 'Long' else 'ШОРТ'}\n"
        f"Вход: ${entry_price:.2f}\n"
        f"Размер: {qty:.6f}\n"
        f"Плечо: {leverage}x\n"
        f"Стоп-лосс: ${stop_loss:.2f}\n"
        f"Тейк-профит: ${take_profit:.2f}\n"
        f"Риск: ${risk_amount:.2f}\n"
        f"💰 Чистая прибыль: {net_profit_percent:.2f}% (с учетом комиссий: вход мейкер 0.02% + выход тейкер 0.055%)\n"
        f"{ai_note}"
        f"{missing_data_note}"
        f"ID ордера: {order_result.get('orderId', 'N/A')}\n\n"
        f"🔔 Мониторинг: /monitor start"
    )


def _determine_trade_side(status: Optional[str], trend: Optional[str]) -> str:
    """
    Логика выбора направления сделки с учетом перекупленности/перепроданности:
      - OVERBOUGHT → Short (но если тренд сильный бычий, может быть Long)
      - OVERSOLD → Long (но если тренд сильный медвежий, может быть Short)
      - BALANCED/NEUTRAL → Long по умолчанию (бычий рынок в целом)
      - Медвежий тренд → Short
      - Бычий тренд → Long
    """
    status = (status or "BALANCED").upper()
    trend = (trend or "сбалансирован").lower()

    # Явная перепроданность - хорошая возможность для Long
    if status == "OVERSOLD":
        # Если тренд очень медвежий, может быть опасно открывать Long
        if "сильный медвеж" in trend or "критическ" in trend:
            return "Short"  # Следуем тренду
        return "Long"  # Перепроданность = возможность для отскока
    
    # Явная перекупленность - возможность для Short
    if status == "OVERBOUGHT":
        # Если тренд очень бычий, может быть опасно открывать Short
        if "сильный быч" in trend or "критическ" in trend:
            return "Long"  # Следуем тренду
        return "Short"  # Перекупленность = возможность для коррекции
    
    # Если статус BALANCED или NEUTRAL, смотрим на тренд
    if "медвеж" in trend:
        return "Short"
    if "быч" in trend:
        return "Long"
    
    # По умолчанию Long (бычий рынок в целом)
    return "Long"


async def _send_long_message(update: Update, message: str):
    """Отправить длинное сообщение, если оно превышает лимиты Telegram."""
    if len(message) > 4000:
        parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(message)


def _ensure_job_queue(application) -> Optional[JobQueue]:
    """Гарантировать наличие JobQueue (для /monitor)."""
    job_queue = getattr(application, "job_queue", None)
    if job_queue is None:
        job_queue = JobQueue()
        job_queue.set_application(application)
        job_queue.start()
        application.job_queue = job_queue
        logger.info("JobQueue создан вручную")
    return job_queue


async def monitor_active_positions(context: ContextTypes.DEFAULT_TYPE):
    """Фоновый мониторинг активных позиций каждые 5 минут (по запросу)."""
    if not ALLOWED_CHAT_IDS:
        return

    bot = context.bot
    try:
        positions = bybit_service.get_positions() or []
    except Exception as e:
        logger.error(f"Мониторинг: не удалось получить позиции: {e}")
        return

    positions_by_symbol = {
        pos.get("symbol"): pos
        for pos in positions
        if pos.get("symbol") and float(pos.get("size") or pos.get("qty") or 0) != 0
    }

    timestamp = datetime.now().strftime("%d.%m %H:%M")

    # ВАЖНО: Проверяем и переустанавливаем условные ордера, если их нет
    # Это гарантирует, что тейк-профит и стоп-лосс всегда работают автоматически
    for symbol, position_meta in positions_by_symbol.items():
        try:
            size = float(position_meta.get("size", 0) or 0)
            if abs(size) < 0.001:
                continue
            
            # Получаем данные для расчета стопов и тейков
            data = market_analysis_service.get_historical_data(symbol)
            if not data:
                continue
            
            exit_plan = _build_exit_plan(symbol, data, position_meta)
            stop_loss = exit_plan.get("stop_loss")
            take_profit = exit_plan.get("take_profit")
            
            # Проверяем, установлены ли стоп-лосс и тейк-профит в позиции
            current_stop = position_meta.get("stopLoss")
            current_tp = position_meta.get("takeProfit")
            
            # Если стоп-лосс или тейк-профит не установлены, устанавливаем их
            if stop_loss and not current_stop:
                logger.info(f"🔄 Устанавливаю стоп-лосс для {symbol}: ${stop_loss}")
                bybit_service.update_stop_loss(symbol, stop_loss)
            
            if take_profit and not current_tp:
                logger.info(f"🔄 Устанавливаю тейк-профит для {symbol}: ${take_profit}")
                # Устанавливаем тейк-профит через set_trading_stop
                bybit_service.set_trading_stop(
                    symbol=symbol,
                    take_profit=take_profit
                )
        except Exception as e:
            logger.warning(f"Мониторинг: ошибка при проверке условных ордеров для {symbol}: {e}")

    # Проверка ликвидаций и профитов
    await _check_position_events(bot, positions_by_symbol)

    if not positions_by_symbol:
        logger.debug("Мониторинг: активных позиций нет — отправляю уведомление")
        no_position_msg = (
            f"⏱ Мониторинг ({timestamp})\n"
            "Сейчас открытых позиций нет, поэтому сигналов нет. Как только появятся сделки, отчёты возобновятся автоматически."
        )
        for chat_id in ALLOWED_CHAT_IDS:
            await _send_text_chunks(bot, chat_id, no_position_msg)
        return

    message_parts = [
        f"⏱ Мониторинг активных монет ({timestamp})",
        f"Монеты: {', '.join(sorted(positions_by_symbol.keys()))}"
    ]

    for symbol, position_meta in positions_by_symbol.items():
        message_parts.append(_build_monitoring_report(symbol, position_meta))
        # Обновляем состояние позиции
        _update_position_state(symbol, position_meta)

    full_message = "\n".join(message_parts)

    for chat_id in ALLOWED_CHAT_IDS:
        await _send_text_chunks(bot, chat_id, full_message)


async def position_poll_job(context: ContextTypes.DEFAULT_TYPE):
    """Проверка состояния позиций каждые 30 секунд."""
    if not ALLOWED_CHAT_IDS:
        return
    
    bot = context.bot
    try:
        positions = bybit_service.get_positions() or []
    except Exception as e:
        logger.error(f"position_poll_job: не удалось получить позиции: {e}")
        return
    
    active_positions = {
        pos.get("symbol"): pos
        for pos in positions
        if pos.get("symbol") and _is_position_active(pos)
    }
    
    # Новые позиции
    for symbol, position_meta in active_positions.items():
        prev_state = POSITION_STATES.get(symbol, {})
        was_active = abs(prev_state.get("last_size", 0.0)) > 0.0001
        if not was_active:
            await _notify_position_opened(bot, symbol, position_meta)
        _update_position_state(symbol, position_meta)
    
    # Закрытые позиции
    for symbol, state in list(POSITION_STATES.items()):
        prev_size = state.get("last_size", 0.0)
        if abs(prev_size) > 0.0001 and symbol not in active_positions:
            await _notify_position_closed(bot, symbol, state)
            POSITION_STATES[symbol]["last_size"] = 0.0
    
    # Проверяем события (ликвидации, профиты)
    await _check_position_events(bot, active_positions)


async def data_collection_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Фоновый job для наполнения БД данными каждую минуту.
    Собирает данные по всем популярным монетам и сохраняет в БД.
    """
    if not db_service or not db_service.connection or not db_service.connection.is_connected():
        return
    
    try:
        logger.info("🔄 Начало сбора данных для БД...")
        
        # Очищаем истекший кэш
        db_service.cleanup_expired_cache()
        
        # Собираем данные по всем популярным монетам
        symbols = market_analysis_service.popular_coins
        collected = 0
        errors = 0
        
        for symbol in symbols:
            try:
                # Получаем данные
                ticker = bybit_service.get_ticker(symbol)
                if not ticker:
                    logger.warning(f"⚠️ Не удалось получить ticker для {symbol}")
                    errors += 1
                    continue
                
                funding = bybit_service.get_funding_rate(symbol)
                oi = bybit_service.get_open_interest(symbol)
                
                # Сохраняем в кэш для быстрого доступа
                cache_data = {
                    "ticker": ticker,
                    "funding": funding,
                    "open_interest": oi,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if db_service:
                    db_service.save_to_cache(symbol, "market_data", cache_data, ttl_minutes=2)
                
                # Получаем исторические данные (они автоматически сохраняются в market_history)
                historical = market_analysis_service.get_historical_data(symbol)
                
                if historical:
                    collected += 1
                else:
                    errors += 1
                    
            except Exception as e:
                logger.error(f"Ошибка при сборе данных для {symbol}: {e}")
                errors += 1
                # Сохраняем ошибку в БД
                if db_service:
                    db_service.save_api_error("data_collection", symbol, "EXCEPTION", str(e))
        
        logger.info(f"✅ Сбор данных завершен: собрано {collected}/{len(symbols)}, ошибок: {errors}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка в data_collection_job: {e}", exc_info=True)


async def data_rotation_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Фоновый job для ротации старых данных в БД.
    Удаляет данные старше 90 дней и старые AI ответы (оставляет последние 1000).
    """
    if not db_service or not db_service.connection or not db_service.connection.is_connected():
        return
    
    try:
        logger.info("🔄 Начало ротации данных в БД...")
        
        # Ротация market_history (храним 90 дней)
        deleted_history = db_service.rotate_old_data("market_history", keep_days=90)
        
        # Ротация api_errors (храним 30 дней)
        deleted_errors = db_service.rotate_old_data("api_errors", keep_days=30)
        
        # Ротация trades_history (храним 90 дней)
        deleted_trades = db_service.rotate_old_data("trades_history", keep_days=90)
        
        # Ротация AI ответов (оставляем последние 1000)
        deleted_ai = db_service.cleanup_old_ai_responses(keep_count=1000)
        
        logger.info(f"✅ Ротация данных завершена: удалено {deleted_history + deleted_errors + deleted_trades + deleted_ai} записей")
        
    except Exception as e:
        logger.error(f"Критическая ошибка в data_rotation_job: {e}", exc_info=True)


async def auto_buy_job(context: ContextTypes.DEFAULT_TYPE):
    """Периодически анализируем рынок и, если автозакупка активна, пробуем открыть сделку."""
    if not AUTO_BUY_STATE["enabled"]:
        return
    
    # При первом запуске авто-бота пытаемся обновить реальные биржевые фильтры объёма,
    # чтобы избежать ошибок Qty invalid из-за неверных локальных настроек.
    if not SYMBOL_FILTERS_REFRESHED:
        _refresh_symbol_filters_from_exchange()
    
    bot = context.bot
    AUTO_BUY_STATE["last_run"] = datetime.utcnow()
    
    try:
        # Ограничиваем время выполнения автозакупки (максимум 25 секунд из 30)
        try:
            trade_msg = await asyncio.wait_for(
                _execute_auto_trade_with_analysis(),
                timeout=25.0
            )
            
            if trade_msg:
                AUTO_BUY_STATE["last_result"] = "открыта новая сделка"
                await _broadcast_message(bot, f"🤖 Автозакупка:\n{trade_msg}")
            else:
                AUTO_BUY_STATE["last_result"] = "сделка не размещена"
        except asyncio.TimeoutError:
            AUTO_BUY_STATE["last_result"] = "таймаут при выполнении"
            error_msg = "Timed out"
            logger.warning(f"Таймаут в auto_buy_job (превышено 25 секунд)")
            await _broadcast_message(bot, f"⚠️ Автозакупка: ошибка\n{error_msg}")
    except Exception as e:
        AUTO_BUY_STATE["last_result"] = f"ошибка: {e}"
        logger.error(f"Ошибка в auto_buy_job: {e}", exc_info=True)
        error_msg = str(e)
        if "Timed out" in error_msg or "timeout" in error_msg.lower():
            error_msg = "Timed out"
        await _broadcast_message(bot, f"⚠️ Автозакупка: ошибка\n{error_msg}")


async def _execute_auto_trade_with_analysis():
    """Вспомогательная функция для выполнения автозакупки с анализом рынка."""
    analysis_results = market_analysis_service.analyze_all_coins()
    if not analysis_results:
        AUTO_BUY_STATE["last_result"] = "нет данных для анализа"
        return None
    
    market_sentiment = news_service.get_market_sentiment() if news_service else None
    overview = market_analysis_service.get_market_overview(analysis_results, market_sentiment)
    if not overview:
        AUTO_BUY_STATE["last_result"] = "нет подходящих активов"
        return None
    
    # Создаем фиктивный update для автозакупки
    class FakeBot:
        pass
    fake_bot = FakeBot()
    proxy_update = SimpleNamespace(message=_BroadcastReplyProxy(fake_bot))
    return await _execute_auto_trade(overview, proxy_update)


def _build_monitoring_report(symbol: str, position_meta: Optional[Dict]) -> str:
    """Собрать отчет по активной монете с историей, стаканом и новостями."""
    try:
        data = market_analysis_service.get_historical_data(symbol)
        if not data:
            return f"\n{symbol}: не удалось получить рыночные данные."

        current_price = data.get("current_price", 0)
        change = data.get("change_24h", 0)
        day_change = data.get("day_change", change)
        week_change = data.get("week_change", 0)
        volatility = data.get("volatility", 0)
        funding = data.get("funding_rate", 0)
        liquidity = data.get("liquidity_score", 0)
        overbought = data.get("overbought_status", "BALANCED")
        status_ru = _translate_status_value(overbought)
        trend = data.get("historical_trend", data.get("price_structure", "нет данных"))
        oi = data.get("open_interest", "N/A")
        volume = market_analysis_service._format_volume_value(data.get("volume_24h", 0)) if hasattr(market_analysis_service, "_format_volume_value") else f"{data.get('volume_24h', 0):,.0f}"

        order_book = bybit_service.get_order_book(symbol) if hasattr(bybit_service, "get_order_book") else None
        buy_qty = order_book.get("total_buy_qty") if order_book else "N/A"
        sell_qty = order_book.get("total_sell_qty") if order_book else "N/A"

        news_summary = ""
        sentiment_line = "• Новости: сервис отключен"
        if news_service:
            try:
                symbol_base = symbol.replace("USDT", "")
                news_ctx = news_service.get_symbol_specific_news(symbol_base, max_results=3)
                sentiment_line = f"• Новости: {news_ctx.get('sentiment', 'NEUTRAL')}"
                first_news = news_ctx.get("news", [])
                if first_news:
                    news_summary = f"{first_news[0].get('title', '')} ({first_news[0].get('source', '')})"
            except Exception as news_error:
                logger.warning(f"Мониторинг: не удалось получить новости для {symbol}: {news_error}")
                sentiment_line = "• Новости: недоступны"

        exit_plan = _build_exit_plan(symbol, data, position_meta)
        orientation_ru = _translate_orientation(exit_plan['orientation'])
        ema_signal_ru = _translate_signal_value(data.get('ema_signal'))
        smart_bias_ru = _translate_signal_value(data.get('smart_money_bias'))
        smart_flow = data.get('smart_money_flow', 0)
        cooldown_remaining = _get_cooldown_remaining(symbol)
        cooldown_line = ""
        if cooldown_remaining:
            minutes_left = int(cooldown_remaining.total_seconds() // 60)
            cooldown_line = f"• ⏸ Пауза активна ещё {minutes_left} мин"

        report = [
            f"\n🔍 {symbol}",
            f"• Цена: ${current_price:.4f} | Изм. 24ч: {change:.2f}% (день {day_change:.2f}%, неделя {week_change:.2f}%)",
            f"• Тренд 1H: {trend}",
            f"• EMA(50/200): {ema_signal_ru} | Отклонение от VWAP: {data.get('vwap_distance', 0):.2f}%",
            f"• Волатильность: {volatility:.2f}% | Фандинг: {funding:.4f}",
            f"• Открытый интерес: {oi} | Ликвидность: {liquidity}/10",
            f"• Объём 24ч: {volume}",
            f"• Заявки в стакане: покупка {buy_qty} / продажа {sell_qty}",
            f"• Состояние: {status_ru}",
            f"• План выхода ({orientation_ru}): тейк ${exit_plan['take_profit']:.4f} / стоп ${exit_plan['stop_loss']:.4f}",
            f"• Крупные игроки: {smart_bias_ru} (нетто {smart_flow:,.0f}$)",
            sentiment_line
        ]
        if cooldown_line:
            report.append(cooldown_line)

        if news_summary:
            report.append(f"  ⚡ {news_summary}")

        return "\n".join(report)
    except Exception as e:
        logger.error(f"Мониторинг: ошибка при формировании отчета для {symbol}: {e}")
        return f"\n{symbol}: ошибка при формировании отчета."


def _build_exit_plan(symbol: str, data: Dict, position_meta: Optional[Dict]) -> Dict:
    """Рассчитать уровни выхода для мониторинга."""
    entry_price = data.get("current_price", 0)
    orientation = "Long"
    if position_meta:
        try:
            entry_price = float(position_meta.get("avgPrice") or position_meta.get("entryPrice") or entry_price)
        except Exception:
            pass
        orientation = _determine_side_from_position(position_meta)

    volatility_percent = max(float(data.get("volatility", 2)) / 100, 0.01)
    historical = data.get("historical") or {}
    atr = historical.get("atr")
    stop_loss = None
    take_profit = None
    if position_meta:
        stop_loss = float(position_meta.get("stopLoss")) if position_meta.get("stopLoss") else None
        take_profit = float(position_meta.get("takeProfit")) if position_meta.get("takeProfit") else None

    if stop_loss is None:
        stop_loss = risk_management_service.get_recommended_stop_loss(entry_price, orientation, volatility_percent, atr)
    if take_profit is None:
        take_profit = risk_management_service.get_recommended_take_profit(entry_price, stop_loss, orientation)

    return {
        "symbol": symbol,
        "orientation": orientation,
        "entry": entry_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss
    }


def _determine_side_from_position(position_meta: Dict) -> str:
    side = (position_meta.get("side") or "").lower()
    if side == "sell":
        return "Short"
    if side == "buy":
        return "Long"
    return "Long"


async def _send_text_chunks(bot, chat_id: int, text: str):
    """Отправка сообщения частями, если превышает лимит."""
    if len(text) <= 4000:
        await bot.send_message(chat_id=chat_id, text=text)
        return

    for i in range(0, len(text), 4000):
        await bot.send_message(chat_id=chat_id, text=text[i:i+4000])


class _BroadcastReplyProxy:
    def __init__(self, bot):
        self.bot = bot
    
    async def reply_text(self, text: str):
        await _broadcast_message(self.bot, text)


def _format_position_side_value(side_value: str) -> str:
    side = (side_value or "").strip().lower()
    if side == "buy":
        return "ЛОНГ"
    if side == "sell":
        return "ШОРТ"
    return "позиция"


def _update_position_state(symbol: str, position_meta: Dict):
    """Обновить состояние позиции для отслеживания событий."""
    if symbol not in POSITION_STATES:
        POSITION_STATES[symbol] = {
            "last_size": 0.0,
            "notified_liquidation": False,
            "notified_profit": False,
            "target_profit": 0.0,
            "entry_price": 0.0,
            "side": ""
        }
    
    current_size = float(position_meta.get("size") or position_meta.get("qty") or 0)
    entry_price = float(position_meta.get("avgPrice") or position_meta.get("entryPrice") or 0)
    POSITION_STATES[symbol]["side"] = position_meta.get("side", POSITION_STATES[symbol].get("side", ""))
    
    POSITION_STATES[symbol]["last_size"] = current_size
    POSITION_STATES[symbol]["entry_price"] = entry_price
    
    # Получаем целевой профит из exit plan
    try:
        data = market_analysis_service.get_historical_data(symbol)
        if data:
            exit_plan = _build_exit_plan(symbol, data, position_meta)
            take_profit_price = exit_plan.get("take_profit", 0)
            if take_profit_price > 0:
                # Рассчитываем целевой процент профита
                if entry_price > 0:
                    if position_meta.get("side", "").lower() == "buy" or current_size > 0:
                        target_pct = ((take_profit_price - entry_price) / entry_price) * 100
                    else:
                        target_pct = ((entry_price - take_profit_price) / entry_price) * 100
                    POSITION_STATES[symbol]["target_profit"] = target_pct
    except Exception as e:
        logger.warning(f"Не удалось обновить target_profit для {symbol}: {e}")


async def _check_position_events(bot, current_positions: Dict[str, Dict]):
    """Проверить события позиций: ликвидация и достижение профита."""
    if not ALLOWED_CHAT_IDS:
        return
    
    for symbol, position_meta in current_positions.items():
        try:
            current_size = float(position_meta.get("size") or position_meta.get("qty") or 0)
            current_price = float(position_meta.get("markPrice") or position_meta.get("mark_price") or 0)
            liq_price = position_meta.get("liqPrice") or position_meta.get("liquidation_price")
            unrealized_pnl = float(position_meta.get("unrealisedPnl") or position_meta.get("unrealized_pnl") or 0)
            entry_price = float(position_meta.get("avgPrice") or position_meta.get("entryPrice") or 0)
            
            if symbol not in POSITION_STATES:
                _update_position_state(symbol, position_meta)
                continue
            
            state = POSITION_STATES[symbol]
            last_size = state.get("last_size", 0.0)
            
            # Проверка ликвидации: позиция закрыта с убытком или цена близка к ликвидации
            if liq_price and liq_price != "N/A":
                try:
                    liq_price_float = float(liq_price)
                    if current_price > 0:
                        distance_to_liq = abs((current_price - liq_price_float) / current_price * 100)
                        
                        # Если позиция закрыта (была, но теперь нет)
                        if abs(last_size) > 0.001 and abs(current_size) < 0.001:
                            if unrealized_pnl < -10:  # Закрыта с убытком
                                if not state.get("notified_liquidation", False):
                                    await _notify_liquidation(bot, symbol, position_meta, unrealized_pnl)
                                    state["notified_liquidation"] = True
                        
                        # Если цена очень близко к ликвидации (< 2%)
                        elif distance_to_liq < 2.0 and not state.get("notified_liquidation", False):
                            await _notify_liquidation_warning(bot, symbol, current_price, liq_price_float, distance_to_liq)
                            state["notified_liquidation"] = True
                except (ValueError, TypeError):
                    pass
            
            # Проверка достижения тейк-профита
            if entry_price > 0 and current_price > 0:
                if current_size > 0:  # Long
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:  # Short
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                target_profit = state.get("target_profit", 0.0)
                
                # Если позиция закрыта с прибылью
                if abs(last_size) > 0.001 and abs(current_size) < 0.001:
                    if unrealized_pnl > 10:  # Закрыта с прибылью
                        if not state.get("notified_profit", False):
                            await _notify_profit_success(bot, symbol, position_meta, unrealized_pnl, pnl_pct)
                            state["notified_profit"] = True
                
                # Если достигнут целевой профит (80% от цели)
                elif target_profit > 0 and pnl_pct >= target_profit * 0.8 and not state.get("notified_profit", False):
                    await _notify_profit_target(bot, symbol, pnl_pct, target_profit, unrealized_pnl)
                    state["notified_profit"] = True
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке событий позиции {symbol}: {e}")


async def _notify_liquidation(bot, symbol: str, position_meta: Dict, pnl: float):
    """Уведомить о ликвидации позиции."""
    message = (
        f"⚠️ ЛИКВИДАЦИЯ: {symbol}\n\n"
        f"Позиция закрыта с убытком: ${pnl:.2f}\n"
        f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"💡 Рекомендации:\n"
        f"- Проверьте размер позиции и leverage\n"
        f"- Убедитесь, что стоп-лосс установлен\n"
        f"- Рассмотрите снижение риска на сделку"
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)


async def _notify_liquidation_warning(bot, symbol: str, current_price: float, liq_price: float, distance_pct: float):
    """Уведомить о приближении к ликвидации."""
    message = (
        f"🚨 ПРЕДУПРЕЖДЕНИЕ: {symbol} близко к ликвидации!\n\n"
        f"Текущая цена: ${current_price:.4f}\n"
        f"Цена ликвидации: ${liq_price:.4f}\n"
        f"Расстояние: {distance_pct:.2f}%\n\n"
        f"⚠️ Рекомендуется:\n"
        f"- Закрыть часть позиции\n"
        f"- Добавить маржу\n"
        f"- Установить стоп-лосс ближе"
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)


async def _notify_profit_success(bot, symbol: str, position_meta: Dict, pnl: float, pnl_pct: float):
    """Уведомить об успешном закрытии позиции с прибылью."""
    entry_price = float(position_meta.get("avgPrice") or position_meta.get("entryPrice") or 0)
    side = "ЛОНГ" if float(position_meta.get("size") or 0) > 0 else "ШОРТ"
    
    message = (
        f"✅ ПРОФИТ: {symbol} закрыта успешно!\n\n"
        f"Тип: {side}\n"
        f"Цена входа: ${entry_price:.4f}\n"
        f"Прибыль: ${pnl:.2f} ({pnl_pct:.2f}%)\n"
        f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"🎉 Отличная работа!"
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)


async def _notify_profit_target(bot, symbol: str, current_pnl_pct: float, target_pnl_pct: float, unrealized_pnl: float):
    """Уведомить о достижении целевого профита."""
    progress = (current_pnl_pct / target_pnl_pct * 100) if target_pnl_pct > 0 else 0
    
    message = (
        f"🎯 ЦЕЛЕВОЙ ПРОФИТ: {symbol}\n\n"
        f"Текущая прибыль: {current_pnl_pct:.2f}% (${unrealized_pnl:.2f})\n"
        f"Целевая прибыль: {target_pnl_pct:.2f}%\n"
        f"Прогресс: {progress:.1f}%\n\n"
        f"💡 Рекомендации:\n"
        f"- Рассмотрите частичное закрытие (50%)\n"
        f"- Переместите стоп-лосс в безубыток\n"
        f"- Оставьте остаток до полного тейк-профита"
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)


async def _notify_position_opened(bot, symbol: str, position_meta: Dict):
    side_display = _format_position_side_value(position_meta.get("side", ""))
    size = abs(float(position_meta.get("size") or position_meta.get("qty") or 0))
    entry_price = float(position_meta.get("avgPrice") or position_meta.get("entryPrice") or 0)
    leverage = position_meta.get("leverage", "N/A")
    stop_loss = position_meta.get("stopLoss") or position_meta.get("slPrice") or "—"
    take_profit = position_meta.get("takeProfit") or position_meta.get("tpPrice") or "—"
    
    message = (
        f"🚀 Открыта позиция: {symbol}\n\n"
        f"Тип: {side_display}\n"
        f"Размер: {size:.6f}\n"
        f"Цена входа: ${entry_price:.4f}\n"
        f"Плечо: {leverage}x\n"
        f"SL: {stop_loss} | TP: {take_profit}\n"
        f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)


async def _notify_position_closed(bot, symbol: str, state: Dict):
    side_display = _format_position_side_value(state.get("side", ""))
    last_size = abs(state.get("last_size", 0.0))
    entry_price = state.get("entry_price", 0.0)
    
    # Получаем текущую цену для расчета PnL
    try:
        ticker = bybit_service.get_ticker(symbol)
        exit_price = float(ticker.get("last_price", 0)) if ticker else entry_price
        
        # Рассчитываем PnL
        side = state.get("side", "Long")
        if side == "Long":
            pnl = (exit_price - entry_price) * last_size
            pnl_percent = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        else:
            pnl = (entry_price - exit_price) * last_size
            pnl_percent = ((entry_price - exit_price) / entry_price * 100) if entry_price > 0 else 0
    except Exception as e:
        logger.warning(f"Не удалось рассчитать PnL для {symbol}: {e}")
        exit_price = entry_price
        pnl = 0.0
        pnl_percent = 0.0
    
    # Обновляем сделку в БД
    if db_service:
        try:
            bot_name = getattr(config, "BOT_NAME", "main")
            db_service.update_trade_exit(
                symbol=symbol,
                exit_price=exit_price,
                pnl=pnl,
                pnl_percent=pnl_percent,
                bot_name=bot_name
            )
            logger.info(f"💾 Сделка обновлена в БД: {symbol} закрыта, PnL: {pnl:.2f} USDT")
        except Exception as e:
            logger.warning(f"Не удалось обновить сделку в БД: {e}")
    
    message = (
        f"🛑 Позиция закрыта: {symbol}\n\n"
        f"Тип: {side_display}\n"
        f"Размер последней позиции: {last_size:.6f}\n"
        f"Цена входа: ${entry_price:.4f}\n"
        f"Цена выхода: ${exit_price:.4f}\n"
        f"P&L: ${pnl:.2f} ({pnl_percent:+.2f}%)\n"
        f"Время: {datetime.now().strftime('%d.%м.%Y %H:%M:%S')}\n\n"
        "ℹ️ Детали по итоговому P&L смотрите в истории сделок Bybit."
    )
    for chat_id in ALLOWED_CHAT_IDS:
        await bot.send_message(chat_id=chat_id, text=message)
    
    # Обновляем время последней сделки, чтобы карантин отсчитывался с момента закрытия
    _record_trade_timestamp(symbol)


async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включить или остановить мониторинг активных монет."""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return

    action = context.args[0].lower() if context.args else "start"
    job_queue = _ensure_job_queue(context.application)

    if not job_queue:
        await update.message.reply_text("❌ Не удалось инициализировать JobQueue. Мониторинг недоступен.")
        return

    existing_jobs = job_queue.get_jobs_by_name(MONITOR_JOB_NAME)

    if action == "stop":
        if not existing_jobs:
            await update.message.reply_text("🛑 Мониторинг уже остановлен.")
            return
        for job in existing_jobs:
            job.schedule_removal()
        await update.message.reply_text("🛑 Мониторинг остановлен. Повторно запустить: /monitor start")
        return

    if existing_jobs:
        next_run = existing_jobs[0].next_t.strftime("%H:%M:%S") if existing_jobs[0].next_t else "скоро"
        await update.message.reply_text(f"🔁 Мониторинг уже запущен. Следующее обновление в {next_run}. Для остановки: /monitor stop")
        return

    job_queue.run_repeating(
        monitor_active_positions,
        interval=MONITOR_INTERVAL_SECONDS,
        first=5,
        name=MONITOR_JOB_NAME
    )
    await update.message.reply_text("✅ Мониторинг активных монет запущен. Отчёты каждые 5 минут. Для остановки: /monitor stop")


async def _handle_auto_buy(update: Update, action: str):
    action = (action or "status").lower()
    message = ""
    if action == "start":
        AUTO_BUY_STATE["enabled"] = True
        message = "🟢 Автозакупка запущена.\n" + _format_auto_buy_status()
    elif action == "stop":
        AUTO_BUY_STATE["enabled"] = False
        message = "🔴 Автозакупка остановлена.\n" + _format_auto_buy_status()
    else:
        message = _format_auto_buy_status()
    await update.message.reply_text(message, reply_markup=_get_command_keyboard())


async def auto_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.args[0] if context.args else "status"
    await _handle_auto_buy(update, action)


async def start_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_auto_buy(update, "start")


async def stop_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_auto_buy(update, "stop")


async def auto_buy_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_auto_buy(update, "status")


async def _initiate_manual_order(action: str, update_or_message, context: ContextTypes.DEFAULT_TYPE, symbol: str, qty: float) -> bool:
    """Общая логика подготовки ручной покупки/продажи."""
    if hasattr(update_or_message, "effective_chat"):
        chat_id = update_or_message.effective_chat.id
        responder = update_or_message.message.reply_text if hasattr(update_or_message, "message") else update_or_message.reply_text
    else:
        chat_id = update_or_message.chat_id
        responder = update_or_message.reply_text
    
    if not check_access(chat_id):
        return False
    
    symbol = symbol.upper()
    if qty <= 0:
        await responder("❌ Количество должно быть больше 0")
        return False
    
    if action == "buy":
        block_reason = _check_symbol_quarantine(symbol)
        if block_reason:
            await responder(block_reason)
            return False
    else:
        remaining = _get_cooldown_remaining(symbol)
        if remaining:
            wait_until = (datetime.utcnow() + remaining).strftime("%H:%M")
            await responder(
                f"⏸ По {symbol} действует пауза {TRADE_COOLDOWN_HOURS} часа. "
                f"Можно повторить продажу после {wait_until}."
            )
            return False
    
    ticker = bybit_service.get_ticker(symbol)
    price_info = ""
    if ticker:
        last_price = float(ticker['last_price'])
        estimated_value = last_price * qty
        label = "стоимость" if action == "buy" else "выручка"
        price_info = (
            f"Текущая цена: ${last_price:.4f}\n"
            f"Примерная {label}: ${estimated_value:.2f}\n\n"
        )
    
    action_label = "покупку" if action == "buy" else "продажу"
    confirm_command = "/confirm_buy" if action == "buy" else "/confirm_sell"
    await responder(
        f"⚠️ Подтвердите {action_label}:\n\n"
        f"Символ: {symbol}\n"
        f"Количество: {qty}\n"
        f"{price_info}"
        f"Отправьте {confirm_command} для подтверждения"
    )
    
    context.user_data['pending_order'] = {
        'action': action,
        'symbol': symbol,
        'qty': qty
    }
    return True
async def trade_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline-кнопки Купить/Продать."""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    chat_id = query.message.chat_id if query.message else None
    if chat_id and not check_access(chat_id):
        await query.answer("Нет доступа", show_alert=True)
        return
    
    action = query.data.split(":")[1]
    context.user_data.pop("pending_order", None)
    context.user_data['trade_mode'] = action
    prompt = "покупки" if action == "buy" else "продажи"
    await query.message.reply_text(
        f"✍️ Введите символ и объём для {prompt} через пробел.\nНапример: BTCUSDT 0.1"
    )


async def _process_trade_input(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, user_text: str) -> bool:
    """Обработка текста после нажатия кнопки Купить/Продать."""
    parts = user_text.replace(",", " ").split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Формат: SYMBOL КОЛИЧЕСТВО. Пример: BTCUSDT 0.1")
        return False
    
    symbol = parts[0].upper()
    qty_str = parts[1]
    try:
        qty = float(qty_str)
    except ValueError:
        await update.message.reply_text("❌ Количество должно быть числом. Пример: 0.1")
        return False
    
    success = await _initiate_manual_order(action, update, context, symbol, qty)
    if success:
        context.user_data.pop("trade_mode", None)
    return success


async def command_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик основных inline-кнопок команд."""
    query = update.callback_query
    if not query or not query.data:
        return
    
    await query.answer()
    data = query.data.split(":", 1)
    if len(data) != 2:
        return
    action_type, action_value = data
    
    chat_id = query.message.chat_id if query.message else None
    if chat_id and not check_access(chat_id):
        await query.answer("Нет доступа", show_alert=True)
        return
    
    if action_type == "input":
        context.user_data["input_mode"] = action_value
        if action_value == "price":
            prompt = "✍️ Введите символ для запроса цены (например: BTCUSDT). Для отмены напишите «отмена»."
        else:
            prompt = "✍️ Введите символ для AI-анализа (например: BTCUSDT). Для отмены напишите «отмена»."
        await query.message.reply_text(prompt)
        return
    
    if action_type != "cmd":
        return
    
    fake_update = _build_callback_update(query)
    
    if action_value == "market_overview":
        await get_market_overview(fake_update, context)
    elif action_value == "positions":
        await get_positions(fake_update, context)
    elif action_value == "update_tp_sl":
        await update_tp_sl_command(fake_update, context)
    elif action_value == "close_all":
        await close_all_positions(fake_update, context)
    elif action_value == "start_buy":
        await _handle_auto_buy(fake_update, "start")
    elif action_value == "stop_buy":
        await _handle_auto_buy(fake_update, "stop")
    elif action_value == "auto_status":
        await _handle_auto_buy(fake_update, "status")
    elif action_value == "monitor_start":
        await monitor_command(fake_update, _ContextArgsProxy(context, ["start"]))
    elif action_value == "monitor_stop":
        await monitor_command(fake_update, _ContextArgsProxy(context, ["stop"]))
    elif action_value == "balance":
        await get_balance(fake_update, context)
    elif action_value == "help":
        await help_command(fake_update, context)


async def buy_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите символ и количество. Пример: /buy BTCUSDT 0.001")
        return
    
    symbol = context.args[0].upper()
    try:
        qty = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат количества")
        return
    
    await _initiate_manual_order("buy", update, context, symbol, qty)


async def sell_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /sell"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите символ и количество. Пример: /sell BTCUSDT 0.001")
        return
    
    symbol = context.args[0].upper()
    try:
        qty = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат количества")
        return
    
    await _initiate_manual_order("sell", update, context, symbol, qty)


async def confirm_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение покупки"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if 'pending_order' not in context.user_data:
        await update.message.reply_text("❌ Нет ожидающих ордеров")
        return
    
    order_data = context.user_data['pending_order']
    if order_data['action'] != 'buy':
        await update.message.reply_text("❌ Это не ордер на покупку")
        return
    
    block_reason = _check_symbol_quarantine(order_data['symbol'])
    if block_reason:
        await update.message.reply_text(block_reason)
        context.user_data.pop('pending_order', None)
        return
    
    # Размещаем ордер с защитными уровнями если они указаны
    result = bybit_service.place_order(
        symbol=order_data['symbol'],
        side="Buy",
        qty=order_data['qty'],
        stop_loss=order_data.get('stop_loss'),
        take_profit=order_data.get('take_profit')
    )
    
    if result and not result.get("error"):
        await update.message.reply_text(
            f"✅ Ордер на покупку размещен!\n\n"
            f"ID ордера: {result.get('orderId', 'N/A')}\n"
            f"Символ: {order_data['symbol']}\n"
            f"Количество: {order_data['qty']}"
        )
        # Карантин устанавливается при ЗАКРЫТИИ позиции, а не при открытии
        if not result.get("tp_sl_attached"):
            _schedule_tp_sl_refresh(order_data['symbol'])
    else:
        error_text = result.get("error") if isinstance(result, dict) else "Bybit вернул ошибку."
        await update.message.reply_text(f"❌ Не удалось разместить ордер: {error_text}")
    
    # Очищаем данные
    context.user_data.pop('pending_order', None)


async def close_all_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Закрыть все открытые позиции"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    await update.message.reply_text("🔄 Закрываю все открытые позиции...")
    
    try:
        result = bybit_service.close_all_positions()
        
        if result["total_closed"] > 0:
            closed_list = "\n".join([
                f"• {p['symbol']}: {p['size']:.6f} ({p['side']})"
                for p in result["closed"]
            ])
            message = (
                f"✅ Закрыто позиций: {result['total_closed']}\n\n"
                f"{closed_list}"
            )
            
            # Устанавливаем карантин для каждого закрытого символа
            for p in result["closed"]:
                symbol = p.get("symbol")
                if symbol:
                    _record_trade_timestamp(symbol)
                    logger.info(f"Карантин установлен для {symbol} после закрытия всех позиций")
            
            if result["errors"]:
                message += f"\n\n⚠️ Ошибки:\n" + "\n".join(result["errors"])
        else:
            message = "📭 Нет открытых позиций для закрытия."
            if result["errors"]:
                message += f"\n\n⚠️ Ошибки:\n" + "\n".join(result["errors"])
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Ошибка при закрытии всех позиций: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при закрытии позиций: {str(e)}")


async def confirm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение продажи"""
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    if 'pending_order' not in context.user_data:
        await update.message.reply_text("❌ Нет ожидающих ордеров")
        return
    
    order_data = context.user_data['pending_order']
    if order_data['action'] != 'sell':
        await update.message.reply_text("❌ Это не ордер на продажу")
        return
    
    # Размещаем ордер с защитными уровнями если они указаны
    result = bybit_service.place_order(
        symbol=order_data['symbol'],
        side="Sell",
        qty=order_data['qty'],
        stop_loss=order_data.get('stop_loss'),
        take_profit=order_data.get('take_profit')
    )
    
    if result and not result.get("error"):
        await update.message.reply_text(
            f"✅ Ордер на продажу размещен!\n\n"
            f"ID ордера: {result.get('orderId', 'N/A')}\n"
            f"Символ: {order_data['symbol']}\n"
            f"Количество: {order_data['qty']}"
        )
        _record_trade_timestamp(order_data['symbol'])
        if not result.get("tp_sl_attached"):
            _schedule_tp_sl_refresh(order_data['symbol'])
    else:
        error_text = result.get("error") if isinstance(result, dict) else "Bybit вернул ошибку."
        await update.message.reply_text(f"❌ Не удалось разместить ордер: {error_text}")
    
    # Очищаем данные
    context.user_data.pop('pending_order', None)


async def update_tp_sl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Автоматически обновить тейк-профит и стоп-лосс для всех открытых позиций
    Использует новую логику: 0.5% брутто-прибыль, AI-анализ, технические индикаторы
    """
    chat_id = update.effective_chat.id
    if not check_access(chat_id):
        return
    
    await update.message.reply_text("⏳ Анализирую открытые позиции и обновляю уровни выхода...")
    
    try:
        # Получаем все открытые позиции
        positions = bybit_service.get_positions() or []
        
        # Логируем для диагностики
        logger.info(f"Получено позиций от API: {len(positions)}")
        for pos in positions:
            symbol = pos.get("symbol", "N/A")
            size = pos.get("size", "N/A")
            size_float = float(size) if size and size != "N/A" else 0
            logger.info(f"Позиция: {symbol}, size={size} (float={size_float})")
        
        active_positions = []
        for pos in positions:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            
            # Пробуем разные варианты получения размера
            size = pos.get("size") or pos.get("qty") or pos.get("positionSize") or "0"
            try:
                size_float = float(size) if size else 0
            except (ValueError, TypeError):
                size_float = 0
            
            # Проверяем, есть ли позиция (размер не равен нулю)
            if abs(size_float) > 0.0001:  # Более мягкое условие
                active_positions.append(pos)
                logger.info(f"Активная позиция найдена: {symbol}, size={size_float}")
        
        logger.info(f"Найдено активных позиций: {len(active_positions)}")
        
        if not active_positions:
            # Показываем детальную информацию для диагностики
            debug_info = f"📭 Нет открытых позиций для обновления\n\n"
            if positions:
                debug_info += f"Получено позиций от API: {len(positions)}\n"
                for pos in positions[:3]:
                    symbol = pos.get("symbol", "N/A")
                    size = pos.get("size", "N/A")
                    debug_info += f"• {symbol}: size={size}\n"
            else:
                debug_info += "API не вернул позиций"
            await update.message.reply_text(debug_info)
            return
        
        results = []
        errors = []
        
        for position in active_positions:
            symbol = position.get("symbol")
            try:
                # Получаем данные для анализа
                data = market_analysis_service.get_historical_data(symbol)
                if not data:
                    errors.append(f"{symbol}: не удалось получить данные")
                    continue
                
                # Определяем тип позиции, полагаясь на side из Bybit (Buy/Long, Sell/Short)
                size = float(position.get("size", 0) or 0)
                logger.info(f"update_tp_sl: позиция {symbol}: {position}")
                raw_position_side = position.get("side")
                position_side = (raw_position_side or "").strip().lower()
                logger.info(
                    f"update_tp_sl: {symbol} raw_side={raw_position_side}, "
                    f"normalized={position_side}, positionIdx={position.get('positionIdx')}, size={size}"
                )
                if position_side == "buy":
                    side = "Long"
                elif position_side == "sell":
                    side = "Short"
                else:
                    # Фолбэк: определяем по ожидаемому PnL (нежелательно, но на случай отсутствия side)
                    side = "Long" if position.get("positionIdx") in (0, 1) else "Short"
                logger.info(f"update_tp_sl: {symbol} interpreted side={side}")
                
                # Получаем цену входа
                entry_price = float(position.get("avgPrice") or position.get("entryPrice") or data.get("current_price", 0))
                if entry_price <= 0:
                    errors.append(f"{symbol}: не удалось определить цену входа")
                    continue
                
                # Рассчитываем новые уровни по новой логике
                volatility_percent = max(data.get("volatility", 2) / 100, 0.01)
                historical = data.get("historical") or {}
                atr = historical.get("atr")
                
                # Стоп-лосс с учетом волатильности/ATR и уровней поддержки/сопротивления
                stop_loss = risk_management_service.get_recommended_stop_loss(
                    entry_price, side, volatility_percent, atr
                )
                
                # Тейк-профит для 0.5% брутто-прибыли
                target_gross_pnl = 0.5  # 0.5% брутто
                if side == "Long":
                    take_profit = entry_price * (1 + target_gross_pnl / 100)
                else:
                    take_profit = entry_price * (1 - target_gross_pnl / 100)
                
                # Обновляем уровни
                result = bybit_service.update_tp_sl(symbol, stop_loss, take_profit)
                
                if result.get("stop_loss") or result.get("take_profit"):
                    result_info = f"✅ {symbol}:\n"
                    if result.get("stop_loss"):
                        result_info += f"  Стоп: ${result['stop_loss']:.4f}\n"
                    if result.get("take_profit"):
                        result_info += f"  Тейк: ${result['take_profit']:.4f}"
                    results.append(result_info)
                    
                    if result.get("errors"):
                        errors.extend([f"{symbol}: {err}" for err in result["errors"]])
                else:
                    errors.append(f"{symbol}: не удалось обновить уровни")
                    
            except Exception as e:
                logger.error(f"Ошибка при обновлении {symbol}: {e}", exc_info=True)
                errors.append(f"{symbol}: {str(e)}")
        
        # Формируем итоговое сообщение
        message_parts = []
        if results:
            message_parts.append("✅ Обновлено позиций: " + str(len(results)))
            message_parts.append("")
            message_parts.extend(results)
        
        if errors:
            message_parts.append("")
            message_parts.append("⚠️ Ошибки:")
            message_parts.extend([f"  • {err}" for err in errors])
        
        if message_parts:
            await update.message.reply_text("\n".join(message_parts))
        else:
            await update.message.reply_text("❌ Не удалось обновить ни одну позицию")
            
    except Exception as e:
        logger.error(f"Ошибка в update_tp_sl_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при обновлении уровней: {str(e)}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений"""
    chat_id = update.effective_chat.id
    message_text = update.message.text if update.message and update.message.text else "N/A"
    
    # Пропускаем команды - они должны обрабатываться CommandHandler
    if message_text.startswith('/'):
        logger.warning(f"⚠️ Команда попала в handle_message (не должна): {message_text}")
        # Не отвечаем на команды здесь - они уже обработаны
        return
    
    logger.info(f"Получено текстовое сообщение (не команда) от {update.effective_user.id} (chat_id: {chat_id}): {message_text}")
    
    if not check_access(chat_id):
        return
    
    trade_mode = context.user_data.get("trade_mode")
    if trade_mode:
        message_clean = message_text.strip()
        if message_clean.lower() in ("отмена", "cancel", "стоп"):
            context.user_data.pop("trade_mode", None)
            await update.message.reply_text("❌ Ручная операция отменена.")
            return
        await _process_trade_input(update, context, trade_mode, message_clean)
        return
    
    input_mode = context.user_data.get("input_mode")
    if input_mode:
        message_clean = message_text.strip()
        if not message_clean:
            await update.message.reply_text("❌ Введите символ.")
            return
        if message_clean.lower() in ("отмена", "cancel", "стоп"):
            context.user_data.pop("input_mode", None)
            await update.message.reply_text("❌ Запрос отменён.")
            return
        symbol = message_clean.upper()
        context_proxy = _ContextArgsProxy(context, [symbol])
        if input_mode == "price":
            await get_price(update, context_proxy)
        elif input_mode == "analyze":
            await analyze_market(update, context_proxy)
        context.user_data.pop("input_mode", None)
        return
    
    await update.message.reply_text(
        "Я понимаю только команды. Используйте /help для списка команд."
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    try:
        if update and update.message:
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")


def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчик для логирования всех обновлений
    async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Логирование всех обновлений для отладки"""
        try:
            if update and update.message:
                msg_text = update.message.text or "N/A"
                msg_id = update.message.message_id
                entities = update.message.entities or []
                logger.info(f"📨 ОБНОВЛЕНИЕ: id={msg_id}, text='{msg_text}', entities={len(entities)}")
                if entities:
                    for entity in entities:
                        logger.info(f"   Entity: type={entity.type}, offset={entity.offset}, length={entity.length}")
        except Exception as e:
            logger.error(f"Ошибка в log_update: {e}")
    
    # Регистрируем обработчик для логирования (должен быть первым, group=-1)
    application.add_handler(MessageHandler(filters.ALL, log_update), group=-1)
    
    # Регистрируем обработчики команд (важно: порядок имеет значение!)
    # Команды регистрируются первыми, чтобы они обрабатывались до текстовых сообщений
    logger.info("Регистрация обработчиков команд...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", get_balance))
    application.add_handler(CommandHandler("price", get_price))
    logger.info("Обработчик команды /price зарегистрирован")
    application.add_handler(CommandHandler("analyze", analyze_market))
    application.add_handler(CommandHandler("positions", get_positions))
    application.add_handler(CommandHandler("decisions", get_trading_decisions))
    application.add_handler(CommandHandler("opportunities", get_opportunities))
    application.add_handler(CommandHandler("market_overview", get_market_overview))
    application.add_handler(CommandHandler("news", get_news))
    application.add_handler(CommandHandler("market_sentiment", get_market_sentiment))
    application.add_handler(CommandHandler("monitor", monitor_command))
    application.add_handler(CommandHandler("auto_buy", auto_buy_command))
    application.add_handler(CommandHandler("start_buy", start_buy_command))
    application.add_handler(CommandHandler("stop_buy", stop_buy_command))
    application.add_handler(CommandHandler("auto_status", auto_buy_status_command))
    application.add_handler(CommandHandler("buy", buy_order))
    application.add_handler(CommandHandler("sell", sell_order))
    application.add_handler(CommandHandler("confirm_buy", confirm_buy))
    application.add_handler(CommandHandler("confirm_sell", confirm_sell))
    application.add_handler(CommandHandler("close_all", close_all_positions))
    application.add_handler(CommandHandler("update_tp_sl", update_tp_sl_command))
    application.add_handler(CallbackQueryHandler(command_button_handler, pattern="^(cmd|input):"))
    application.add_handler(CallbackQueryHandler(trade_button_handler, pattern="^trade:"))
    logger.info("Все обработчики команд зарегистрированы")
    
    # Обработчик текстовых сообщений (НЕ команд) - должен быть последним
    # Используем фильтр, который исключает команды
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Обработчик текстовых сообщений зарегистрирован")
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем фоновый опрос позиций каждые 30 секунд
    job_queue = _ensure_job_queue(application)
    if job_queue:
        existing_poll_jobs = job_queue.get_jobs_by_name(POSITION_POLL_JOB_NAME)
        if not existing_poll_jobs:
            job_queue.run_repeating(
                position_poll_job,
                interval=POSITION_POLL_INTERVAL_SECONDS,
                first=5,
                name=POSITION_POLL_JOB_NAME
            )
        existing_auto_jobs = job_queue.get_jobs_by_name(AUTO_BUY_JOB_NAME)
        if not existing_auto_jobs:
            job_queue.run_repeating(
                auto_buy_job,
                interval=AUTO_BUY_INTERVAL_SECONDS,
                first=10,
                name=AUTO_BUY_JOB_NAME
            )
        
        # Регистрируем job для сбора данных в БД
        if db_service and db_service.connection and db_service.connection.is_connected():
            existing_data_jobs = job_queue.get_jobs_by_name(DATA_COLLECTION_JOB_NAME)
            if not existing_data_jobs:
                job_queue.run_repeating(
                    data_collection_job,
                    interval=DATA_COLLECTION_INTERVAL_SECONDS,
                    first=15,  # Запускаем через 15 секунд после старта
                    name=DATA_COLLECTION_JOB_NAME
                )
                logger.info(f"✅ Зарегистрирован job для сбора данных в БД (каждые {DATA_COLLECTION_INTERVAL_SECONDS} сек)")
            
            # Регистрируем job для ротации данных в БД (раз в день)
            existing_rotation_jobs = job_queue.get_jobs_by_name(DATA_ROTATION_JOB_NAME)
            if not existing_rotation_jobs:
                job_queue.run_repeating(
                    data_rotation_job,
                    interval=DATA_ROTATION_INTERVAL_HOURS * 3600,  # Конвертируем часы в секунды
                    first=3600,  # Запускаем через час после старта
                    name=DATA_ROTATION_JOB_NAME
                )
                logger.info(f"✅ Зарегистрирован job для ротации данных в БД (каждые {DATA_ROTATION_INTERVAL_HOURS} часов)")
    
    # Запускаем бота
    logger.info("Бот запущен...")
    logger.info("Ожидание обновлений от Telegram...")
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Удаляем ожидающие обновления при старте
        )
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    main()
