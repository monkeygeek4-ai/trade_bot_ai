#!/usr/bin/env python3
"""
Скрипт для тестирования всех запросов к Bybit API
Проверяет корректность данных и выявляет проблемы с конфигурацией
"""
import sys
import json
from services.bybit_service import BybitService
from services.market_analysis_service import MarketAnalysisService
import config

def test_bybit_methods():
    """Тестирование всех методов BybitService"""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ BYBIT API")
    print("=" * 60)
    print(f"Testnet: {config.BYBIT_TESTNET}")
    print(f"API Key: {config.BYBIT_API_KEY[:10]}..." if config.BYBIT_API_KEY else "NOT SET")
    print()
    
    bybit = BybitService()
    test_symbol = "BTCUSDT"
    
    results = {
        "passed": [],
        "failed": [],
        "warnings": []
    }
    
    # Тест 1: Баланс
    print("1. Тест получения баланса...")
    try:
        balance = bybit.get_balance()
        if balance is not None:
            print(f"   ✅ Баланс: {balance} USDT")
            results["passed"].append("get_balance")
        else:
            print(f"   ❌ Не удалось получить баланс")
            results["failed"].append("get_balance")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_balance")
    print()
    
    # Тест 2: Ticker
    print("2. Тест получения тикера...")
    try:
        ticker = bybit.get_ticker(test_symbol)
        if ticker and ticker.get("last_price"):
            print(f"   ✅ Ticker получен: {ticker.get('symbol')} = ${ticker.get('last_price')}")
            print(f"      Объем 24ч: {ticker.get('volume_24h')}")
            print(f"      Изменение 24ч: {float(ticker.get('change_24h', 0)) * 100:.2f}%")
            results["passed"].append("get_ticker")
        else:
            print(f"   ❌ Ticker пустой или некорректный")
            results["failed"].append("get_ticker")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_ticker")
    print()
    
    # Тест 3: Funding Rate
    print("3. Тест получения funding rate...")
    try:
        funding = bybit.get_funding_rate(test_symbol)
        if funding and funding.get("funding_rate") is not None:
            print(f"   ✅ Funding rate: {float(funding.get('funding_rate', 0)) * 100:.6f}%")
            results["passed"].append("get_funding_rate")
        else:
            print(f"   ⚠️ Funding rate пустой")
            results["warnings"].append("get_funding_rate")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_funding_rate")
    print()
    
    # Тест 4: Open Interest
    print("4. Тест получения open interest...")
    try:
        oi = bybit.get_open_interest(test_symbol)
        if oi and oi.get("open_interest"):
            print(f"   ✅ Open Interest: {oi.get('open_interest')}")
            results["passed"].append("get_open_interest")
        else:
            print(f"   ⚠️ Open Interest пустой")
            results["warnings"].append("get_open_interest")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_open_interest")
    print()
    
    # Тест 5: Kline (свечи)
    print("5. Тест получения свечей...")
    try:
        candles = bybit.get_kline(test_symbol, interval="60", limit=10)
        if candles and len(candles) > 0:
            print(f"   ✅ Получено свечей: {len(candles)}")
            print(f"      Последняя свеча: O={candles[-1]['open']}, H={candles[-1]['high']}, L={candles[-1]['low']}, C={candles[-1]['close']}")
            results["passed"].append("get_kline")
        else:
            print(f"   ❌ Свечи пустые")
            results["failed"].append("get_kline")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_kline")
    print()
    
    # Тест 6: Order Book
    print("6. Тест получения order book...")
    try:
        order_book = bybit.get_order_book(test_symbol, limit=10)
        if order_book and order_book.get("bids") and order_book.get("asks"):
            print(f"   ✅ Order book получен: {len(order_book.get('bids', []))} bids, {len(order_book.get('asks', []))} asks")
            results["passed"].append("get_order_book")
        else:
            print(f"   ⚠️ Order book пустой")
            results["warnings"].append("get_order_book")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_order_book")
    print()
    
    # Тест 7: Позиции
    print("7. Тест получения позиций...")
    try:
        positions = bybit.get_positions()
        if positions is not None:
            active = [p for p in positions if abs(float(p.get("size", 0) or 0)) > 0.0001]
            print(f"   ✅ Получено позиций: {len(positions)} (активных: {len(active)})")
            results["passed"].append("get_positions")
        else:
            print(f"   ⚠️ Позиции пустые")
            results["warnings"].append("get_positions")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_positions")
    print()
    
    # Тест 8: Комплексные данные
    print("8. Тест получения комплексных данных...")
    try:
        market_data = bybit.get_market_data_comprehensive(test_symbol)
        if market_data:
            print(f"   ✅ Комплексные данные получены")
            print(f"      Ticker: {'✅' if market_data.get('ticker') else '❌'}")
            print(f"      Funding: {'✅' if market_data.get('funding') else '❌'}")
            print(f"      OI: {'✅' if market_data.get('open_interest') else '❌'}")
            results["passed"].append("get_market_data_comprehensive")
        else:
            print(f"   ❌ Комплексные данные пустые")
            results["failed"].append("get_market_data_comprehensive")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["failed"].append("get_market_data_comprehensive")
    print()
    
    # Итоги
    print("=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    print(f"✅ Успешно: {len(results['passed'])}")
    print(f"⚠️ Предупреждения: {len(results['warnings'])}")
    print(f"❌ Ошибки: {len(results['failed'])}")
    print()
    
    if results["failed"]:
        print("❌ ПРОВАЛЕННЫЕ ТЕСТЫ:")
        for test in results["failed"]:
            print(f"   - {test}")
        print()
        return False
    
    if results["warnings"]:
        print("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for test in results["warnings"]:
            print(f"   - {test}")
        print()
    
    print("✅ Все критические тесты пройдены!")
    return True

if __name__ == "__main__":
    success = test_bybit_methods()
    sys.exit(0 if success else 1)

