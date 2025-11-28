#!/usr/bin/env python3
"""
Скрипт для загрузки исторических данных для одной монеты
"""
import sys
from datetime import datetime, timedelta
from services.bybit_service import BybitService
from services.market_analysis_service import MarketAnalysisService
from services.db_service import DatabaseService
import config
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_year_of_data(symbol: str, db_service: DatabaseService, 
                     market_service: MarketAnalysisService, bybit_service: BybitService):
    """Загрузить год исторических данных для символа"""
    logger.info(f"📥 Начинаю загрузку данных за год для {symbol}...")
    
    # Определяем период: год назад до сейчас
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=365)
    
    # Интервал 1 час
    interval = "60"
    limit_per_request = 1000
    
    # Рассчитываем количество запросов
    total_hours = int((end_time - start_time).total_seconds() / 3600)
    num_requests = (total_hours + limit_per_request - 1) // limit_per_request
    
    logger.info(f"   Период: {start_time.strftime('%Y-%m-%d')} - {end_time.strftime('%Y-%m-%d')}")
    logger.info(f"   Всего часов: {total_hours}, запросов: {num_requests}")
    
    all_candles = []
    errors = 0
    
    # Конвертируем время в миллисекунды для API
    start_timestamp_ms = int(start_time.timestamp() * 1000)
    end_timestamp_ms = int(end_time.timestamp() * 1000)
    
    # Загружаем свечи порциями с правильными временными метками
    current_end = end_timestamp_ms
    request_num = 0
    
    while current_end > start_timestamp_ms and request_num < num_requests * 2:
        try:
            hours_in_request = limit_per_request
            ms_per_hour = 60 * 60 * 1000
            request_start = current_end - (hours_in_request * ms_per_hour)
            
            if request_start < start_timestamp_ms:
                request_start = start_timestamp_ms
            
            candles = bybit_service.get_kline(
                symbol=symbol,
                interval=interval,
                limit=limit_per_request,
                start_time=request_start,
                end_time=current_end
            )
            
            if not candles:
                logger.warning(f"   ⚠️ Запрос {request_num+1}: пустой ответ")
                errors += 1
                current_end = request_start - ms_per_hour
                time.sleep(1)
                continue
            
            existing_timestamps = {c["timestamp"] for c in all_candles}
            new_candles = [c for c in candles if c["timestamp"] not in existing_timestamps]
            
            if new_candles:
                all_candles.extend(new_candles)
                logger.info(f"   ✅ Запрос {request_num+1}: получено {len(new_candles)} новых свечей (всего {len(all_candles)})")
            else:
                logger.warning(f"   ⚠️ Запрос {request_num+1}: все свечи дубликаты")
            
            if new_candles:
                earliest_timestamp = min(c["timestamp"] for c in new_candles)
                current_end = earliest_timestamp - ms_per_hour
            else:
                current_end = request_start - ms_per_hour
            
            if current_end <= start_timestamp_ms:
                break
            
            request_num += 1
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка при запросе {request_num+1}: {e}")
            errors += 1
            time.sleep(2)
            if 'request_start' in locals():
                current_end = request_start - ms_per_hour
            else:
                break
    
    if not all_candles:
        logger.error(f"❌ Не удалось загрузить данные для {symbol}")
        return False
    
    all_candles.sort(key=lambda x: x["timestamp"])
    
    logger.info(f"   📊 Всего загружено уникальных свечей: {len(all_candles)}")
    
    if all_candles:
        first_candle_time = datetime.fromtimestamp(all_candles[0]["timestamp"] / 1000)
        last_candle_time = datetime.fromtimestamp(all_candles[-1]["timestamp"] / 1000)
        actual_hours = len(all_candles)
        expected_hours = total_hours
        coverage = (actual_hours / expected_hours * 100) if expected_hours > 0 else 0
        logger.info(f"   📈 Покрытие: {first_candle_time.strftime('%Y-%m-%d %H:%M')} - {last_candle_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"   📊 Фактически: {actual_hours} часов, ожидалось: {expected_hours} часов ({coverage:.1f}%)")
    
    saved_count = 0
    errors = 0
    
    logger.info(f"   🔄 Обработка {len(all_candles)} свечей...")
    
    for i, candle in enumerate(all_candles):
        try:
            candle_timestamp = datetime.utcfromtimestamp(candle["timestamp"] / 1000)
            
            market_data = {
                "current_price": candle["close"],
                "volume_24h": candle.get("volume", 0) * 24,
                "volatility": abs((candle["high"] - candle["low"]) / candle["close"] * 100) if candle["close"] > 0 else 0,
                "funding_rate": 0,
                "open_interest": 0,
                "liquidity_score": 0
            }
            
            window_candles = all_candles[max(0, i-200):i+1]
            candle_stats = {}
            
            if len(window_candles) >= 50:
                try:
                    candle_stats = market_service._analyze_candles(window_candles)
                except Exception as e:
                    logger.debug(f"   ⚠️ Не удалось рассчитать индикаторы для свечи {i}: {e}")
            
            if db_service.save_market_snapshot(symbol, market_data, candle_stats):
                saved_count += 1
                
                if saved_count % 500 == 0:
                    logger.info(f"   💾 Сохранено {saved_count} снимков...")
            else:
                errors += 1
            
        except Exception as e:
            logger.warning(f"   ⚠️ Ошибка при обработке свечи {i}: {e}")
            errors += 1
            continue
    
    logger.info(f"✅ Для {symbol} сохранено {saved_count} снимков в БД")
    return saved_count > 0


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "MATICUSDT"
    
    print("=" * 60)
    print(f"ЗАГРУЗКА ИСТОРИЧЕСКИХ ДАННЫХ ДЛЯ {symbol}")
    print("=" * 60)
    print()
    
    try:
        db_service = DatabaseService()
        if not db_service.connection or not db_service.connection.is_connected():
            print("❌ Не удалось подключиться к БД")
            sys.exit(1)
        
        db_service.init_tables()
        print("✅ БД подключена и таблицы инициализированы")
        
        bybit_service = BybitService(db_service=db_service)
        market_service = MarketAnalysisService(db_service=db_service)
        
        print("✅ Сервисы инициализированы")
        print()
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        sys.exit(1)
    
    print(f"📊 Загрузка данных для {symbol}...")
    print()
    
    try:
        success = load_year_of_data(symbol, db_service, market_service, bybit_service)
        if success:
            print(f"✅ {symbol} - успешно загружено")
        else:
            print(f"❌ {symbol} - ошибка загрузки")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка для {symbol}: {e}", exc_info=True)
        print(f"❌ {symbol} - критическая ошибка: {e}")
        sys.exit(1)
    
    print()
    print("💡 Данные успешно загружены в БД!")


if __name__ == "__main__":
    main()

