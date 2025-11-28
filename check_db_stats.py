#!/usr/bin/env python3
"""Проверка статистики загруженных данных в БД"""
from services.db_service import DatabaseService

db = DatabaseService()
if db.connection:
    query = """
    SELECT 
        symbol, 
        COUNT(*) as count, 
        MIN(timestamp) as first_date, 
        MAX(timestamp) as last_date 
    FROM market_history 
    GROUP BY symbol 
    ORDER BY symbol
    """
    result = db.execute_query(query)
    if result:
        print("📊 СТАТИСТИКА ЗАГРУЖЕННЫХ ДАННЫХ:")
        print("=" * 70)
        total = 0
        for row in result:
            count = row['count']
            total += count
            symbol = row['symbol']
            first = row['first_date']
            last = row['last_date']
            print(f"{symbol:12} | {count:6} свечей | {first} - {last}")
        print("=" * 70)
        print(f"Всего: {total} снимков в БД")
        print(f"Монет: {len(result)}")
    else:
        print("Нет данных в БД")
else:
    print("Не удалось подключиться к БД")

