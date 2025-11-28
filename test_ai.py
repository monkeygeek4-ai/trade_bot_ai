#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к AI (DeepSeek / Hugging Face)
"""
import sys
from services.ai_service import AIService


def main():
    print("=" * 50)
    print("Тест подключения к AI (DeepSeek / HF)")
    print("=" * 50)
    print()
    
    # Создаем экземпляр сервиса
    print("Инициализация AI сервиса...")
    ai_service = AIService()
    print(f"✅ Используемая модель: {ai_service.model}")
    print()
    
    # Тест 1: Простой запрос
    print("Тест 1: Простой запрос")
    print("-" * 50)
    try:
        completion = ai_service.client.chat.completions.create(
            model=ai_service.model,
            messages=[
                {
                    "role": "user",
                    "content": "Привет! Как дела? Ответь кратко на русском."
                }
            ],
            max_tokens=100,
            temperature=0.7
        )
        response = completion.choices[0].message.content
        print(f"✅ Запрос выполнен успешно")
        print(f"📝 Ответ AI: {response}")
        print()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print()
        sys.exit(1)
    
    # Тест 2: Анализ рынка
    print("Тест 2: Анализ рыночных данных")
    print("-" * 50)
    try:
        market_data = {
            "symbol": "BTCUSDT",
            "last_price": "45000",
            "change_24h": "0.05",
            "volume_24h": "1000000000"
        }
        
        analysis = ai_service.analyze_market(market_data)
        print(f"✅ Анализ получен")
        print(f"📊 Символ: {market_data['symbol']}")
        print(f"💰 Цена: ${market_data['last_price']}")
        print(f"📈 Изменение 24ч: {float(market_data['change_24h']) * 100:.2f}%")
        print()
        print(f"🤖 AI Рекомендация:")
        print(f"{analysis}")
        print()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print()
        sys.exit(1)
    
    # Тест 3: Торговый совет
    print("Тест 3: Торговый совет")
    print("-" * 50)
    try:
        advice = ai_service.get_trading_advice(
            symbol="BTCUSDT",
            current_price="45000",
            balance="1000"
        )
        print(f"✅ Совет получен")
        print(f"🤖 AI Совет:")
        print(f"{advice}")
        print()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print()
        sys.exit(1)
    
    print("=" * 50)
    print("✅ Все тесты AI пройдены успешно!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

