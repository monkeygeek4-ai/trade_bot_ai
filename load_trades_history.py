#!/usr/bin/env python3
"""
Скрипт для загрузки истории сделок за последние 24 часа из Bybit API в БД
Загружает данные для обоих ботов (main и iliya)
"""
import sys
import os
import time
from datetime import datetime, timedelta
from services.bybit_service import BybitService
from services.db_service import DatabaseService
import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_trades_history_24h(bybit_service: BybitService, db_service: DatabaseService, bot_name: str = "main"):
    """
    Загрузить историю сделок за последние 24 часа из Bybit API
    
    Args:
        bybit_service: Сервис для работы с Bybit API
        db_service: Сервис для работы с БД
        bot_name: Имя бота (main или iliya)
    """
    logger.info(f"📥 Начинаю загрузку истории сделок за 24 часа для бота {bot_name}...")
    
    try:
        # Получаем закрытые позиции (closed PnL) за последние 24 часа
        # Используем get_closed_pnl из Bybit API
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)
        
        start_timestamp_ms = int(start_time.timestamp() * 1000)
        end_timestamp_ms = int(end_time.timestamp() * 1000)
        
        logger.info(f"   Период: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}")
        
        # Получаем закрытые позиции через get_positions и анализируем закрытые
        # Или используем get_closed_pnl если доступен
        try:
            # Пробуем получить закрытые PnL через API
            response = bybit_service.client.get_closed_pnl(
                category="linear",
                startTime=start_timestamp_ms,
                endTime=end_timestamp_ms,
                limit=50
            )
            
            if response.get("retCode") == 0:
                closed_pnls = response.get("result", {}).get("list", [])
                logger.info(f"   Найдено закрытых позиций: {len(closed_pnls)}")
                
                loaded = 0
                for pnl_data in closed_pnls:
                    try:
                        symbol = pnl_data.get("symbol", "")
                        side = "Long" if pnl_data.get("side") == "Buy" else "Short"
                        entry_price = float(pnl_data.get("avgEntryPrice", 0))
                        exit_price = float(pnl_data.get("avgExitPrice", 0))
                        qty = float(pnl_data.get("qty", 0))
                        closed_pnl = float(pnl_data.get("closedPnl", 0))
                        leverage = int(pnl_data.get("leverage", 1))
                        
                        # Рассчитываем PnL в процентах
                        if entry_price > 0:
                            if side == "Long":
                                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
                            else:
                                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
                        else:
                            pnl_percent = 0
                        
                        # Время входа и выхода
                        created_time = int(pnl_data.get("createdTime", 0))
                        updated_time = int(pnl_data.get("updatedTime", 0))
                        
                        entry_time = datetime.fromtimestamp(created_time / 1000) if created_time else start_time
                        exit_time = datetime.fromtimestamp(updated_time / 1000) if updated_time else end_time
                        
                        # Проверяем наличие колонки bot_name
                        check_column = db_service.execute_query(
                            "SHOW COLUMNS FROM trades_history LIKE 'bot_name'"
                        )
                        has_bot_name = check_column and len(check_column) > 0
                        
                        # Проверяем, есть ли уже такая сделка в БД
                        if has_bot_name:
                            check_query = """
                                SELECT id FROM trades_history
                                WHERE symbol = %s AND bot_name = %s 
                                AND entry_time = %s AND exit_time = %s
                                LIMIT 1
                            """
                            existing = db_service.execute_query(
                                check_query,
                                (symbol, bot_name, entry_time, exit_time)
                            )
                        else:
                            check_query = """
                                SELECT id FROM trades_history
                                WHERE symbol = %s 
                                AND entry_time = %s AND exit_time = %s
                                LIMIT 1
                            """
                            existing = db_service.execute_query(
                                check_query,
                                (symbol, entry_time, exit_time)
                            )
                        
                        if not existing or len(existing) == 0:
                            # Сохраняем сделку сначала как открытую
                            trade_id = db_service.save_trade(
                                symbol=symbol,
                                side=side,
                                entry_price=entry_price,
                                quantity=qty,
                                leverage=leverage,
                                bot_name=bot_name,
                                status="open"
                            )
                            
                            # Сразу обновляем как закрытую с выходом
                            if trade_id:
                                db_service.update_trade_exit(
                                    symbol=symbol,
                                    exit_price=exit_price,
                                    pnl=closed_pnl,
                                    pnl_percent=pnl_percent,
                                    bot_name=bot_name
                                )
                            
                            loaded += 1
                            logger.info(f"   ✅ Загружена сделка: {symbol} {side} PnL: {closed_pnl:.2f} USDT")
                        else:
                            logger.debug(f"   ⏭ Пропущена дубликат: {symbol} {side}")
                    
                    except Exception as e:
                        logger.warning(f"   ⚠️ Ошибка при обработке сделки: {e}")
                        continue
                
                logger.info(f"✅ Загружено {loaded} новых сделок для бота {bot_name}")
                return loaded
            
            else:
                logger.warning(f"   ⚠️ API вернул ошибку: {response.get('retMsg')}")
                return 0
        
        except Exception as e:
            logger.warning(f"   ⚠️ Не удалось получить закрытые PnL: {e}")
            logger.info("   Пробую альтернативный метод...")
            
            # Альтернативный метод: получаем текущие позиции и ищем закрытые
            # Это менее точный метод, но может помочь
            try:
                positions = bybit_service.get_positions()
                logger.info(f"   Получено {len(positions) if positions else 0} текущих позиций")
                # Для закрытых позиций нужен другой подход
                return 0
            except Exception as e2:
                logger.error(f"   ❌ Альтернативный метод тоже не сработал: {e2}")
                return 0
    
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке истории сделок для {bot_name}: {e}")
        return 0


def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Загрузка истории сделок из Bybit')
    parser.add_argument('--bot', type=str, default='both', choices=['main', 'iliya', 'both'],
                       help='Какой бот загружать (main, iliya, both)')
    args = parser.parse_args()
    
    logger.info("🚀 Запуск загрузки истории сделок за 24 часа...")
    
    # Инициализация сервисов
    try:
        db_service = DatabaseService()
        if not db_service.connection or not db_service.connection.is_connected():
            logger.error("❌ Не удалось подключиться к БД")
            return
        
        logger.info("✅ Подключение к БД установлено")
        
        main_loaded = 0
        iliya_loaded = 0
        
        # Загружаем для main бота
        if args.bot in ['main', 'both']:
            # Используем основные API ключи из .env
            bybit_main = BybitService(db_service=db_service)
            logger.info("📊 Загрузка для основного бота (main)...")
            main_loaded = load_trades_history_24h(bybit_main, db_service, "main")
        
        # Загружаем для iliya бота
        if args.bot in ['iliya', 'both']:
            logger.info("📊 Загрузка для бота iliya...")
            # Загружаем переменные окружения для iliya бота
            iliya_env_path = "/root/trade_bot_ai_iliya/.env"
            if os.path.exists(iliya_env_path):
                from dotenv import load_dotenv
                # Сохраняем текущие переменные
                old_api_key = os.getenv("BYBIT_API_KEY")
                old_api_secret = os.getenv("BYBIT_API_SECRET")
                old_testnet = os.getenv("BYBIT_TESTNET")
                
                # Загружаем переменные iliya
                load_dotenv(iliya_env_path, override=True)
                logger.info("✅ Загружены переменные окружения для iliya бота")
                
                # Создаем сервис с API ключами iliya
                bybit_iliya = BybitService(db_service=db_service)
                iliya_loaded = load_trades_history_24h(bybit_iliya, db_service, "iliya")
                
                # Восстанавливаем старые переменные (если нужно)
                if old_api_key:
                    os.environ["BYBIT_API_KEY"] = old_api_key
                if old_api_secret:
                    os.environ["BYBIT_API_SECRET"] = old_api_secret
                if old_testnet:
                    os.environ["BYBIT_TESTNET"] = old_testnet
            else:
                logger.warning(f"⚠️  Файл {iliya_env_path} не найден, пропускаем загрузку для iliya")
                iliya_loaded = 0
        
        logger.info(f"✅ Загрузка завершена!")
        logger.info(f"   Main бот: {main_loaded} сделок")
        logger.info(f"   Iliya бот: {iliya_loaded} сделок")
        logger.info(f"   Всего: {main_loaded + iliya_loaded} сделок")
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

