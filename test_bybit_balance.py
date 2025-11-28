#!/usr/bin/env python3
"""
Тест получения баланса через Bybit API
"""
from services.bybit_service import BybitService
import config

print("Тест подключения к Bybit API")
print("=" * 50)
print(f"Testnet: {config.BYBIT_TESTNET}")
print(f"API Key: {config.BYBIT_API_KEY[:10]}...")
print()

try:
    service = BybitService()
    print("✅ BybitService инициализирован")
    print()
    
    print("Попытка получить баланс...")
    balance = service.get_balance()
    
    if balance is not None:
        print(f"✅ Баланс получен: {balance} USDT")
    else:
        print("❌ Не удалось получить баланс")
        print()
        print("Проверьте:")
        print("1. Правильность API ключей")
        print("2. Разрешения API ключа (нужен доступ к чтению баланса)")
        print("3. Если testnet=True, используйте тестовые ключи")
        
except Exception as e:
    print(f"❌ Критическая ошибка: {e}")
    import traceback
    traceback.print_exc()

