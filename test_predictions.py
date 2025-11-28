#!/usr/bin/env python3
"""
Скрипт для тестирования работы предсказаний и комбинированного анализа рынка.

Запускает MarketAnalysisService (техника) + NewsService (новости) и выводит:
 - общий обзор рынка
 - топ-возможности (с риск-профилем)
 - статус перекупленности / перепроданности
 - эмоциональный фон (если доступен API ключ Perplexity)
"""

import json
import sys

try:
    import config
    from services.market_analysis_service import MarketAnalysisService
    from services.news_service import NewsService
except ImportError as exc:
    print(f"❌ Не удалось импортировать модули: {exc}")
    sys.exit(1)


def main():
    # Инициализируем сервисы
    news_service = None
    if getattr(config, "PERPLEXITY_API_KEY", None):
        try:
            news_service = NewsService(api_key=config.PERPLEXITY_API_KEY)
            print("✅ NewsService подключен (Perplexity API).")
        except Exception as exc:
            print(f"⚠️ Не удалось инициализировать NewsService: {exc}")
    else:
        print("⚠️ PERPLEXITY_API_KEY не найден — новостной фон отключен.")

    market_service = MarketAnalysisService(news_service=news_service)
    print("🔎 Запускаю глубокий анализ рынка (топ монеты)...")

    analysis_results = market_service.analyze_all_coins()
    if not analysis_results:
        print("❌ Не удалось получить анализ. Проверьте соединение с Bybit/API ключи.")
        return

    market_sentiment = news_service.get_market_sentiment() if news_service else None
    overview = market_service.get_market_overview(analysis_results, market_sentiment)

    print("\n================= ОБЩИЙ ОБЗОР РЫНКА =================")
    print(json.dumps({
        "avg_volatility": overview.get("avg_volatility"),
        "avg_funding_%": overview.get("avg_funding"),
        "overbought_assets": overview.get("overbought_count"),
        "oversold_assets": overview.get("oversold_count"),
        "total_assets": overview.get("total_assets"),
        "market_sentiment": market_sentiment.get("sentiment") if market_sentiment else "N/A"
    }, indent=2, ensure_ascii=False))

    print("\n================= ТОП ВОЗМОЖНОСТИ (3) =================")
    for idx, asset in enumerate(overview.get("best_assets", [])[:3], start=1):
        data = asset["data"]
        leverage = asset["leverage_info"]["recommended_leverage"]
        status = data.get("overbought_status", "NEUTRAL")
        potential = asset["position_info"].get("potential_profit", 0)

        print(f"\n#{idx}: {asset['symbol']}")
        print(f"  Score: {asset['score']:.1f}")
        print(f"  Цена: ${data['current_price']} | Δ24ч: {data['change_24h']:.2f}%")
        print(f"  Волатильность: {data['volatility']}% | Funding: {data['funding_rate']*100:.4f}%")
        print(f"  Статус: {status}")
        print(f"  Рекомендуемое плечо: {leverage}x")
        print(f"  Потенциальная прибыль (цель 5-10$): ${potential:.2f}")

    print("\n================= ЭМОЦИОНАЛЬНЫЙ ФОН =================")
    if market_sentiment:
        print(f"Настроение рынка: {market_sentiment.get('sentiment')}")
        print("Примеры новостей:")
        for news in market_sentiment.get("news", [])[:3]:
            print(f" - {news.get('title')}")
    else:
        print("⚠️ Новостной фон недоступен (нет PERPLEXITY_API_KEY).")

    print("\n✅ Тест предсказаний завершён.")


if __name__ == "__main__":
    main()

