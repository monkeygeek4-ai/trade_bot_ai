#!/usr/bin/env python3
"""
Скрипт для удаления дубликатов из trades_history
Оставляет только одну запись для каждой уникальной комбинации
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 60)
    print("УДАЛЕНИЕ ДУБЛИКАТОВ ИЗ trades_history")
    print("=" * 60)
    print()
    
    db_config = {
        'host': os.getenv('DB_HOST', '85.198.119.37'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'database': os.getenv('DB_NAME', 'bybit19'),
        'user': os.getenv('DB_USER', 'bybit19_usr'),
        'password': os.getenv('DB_PASSWORD', 'Rjhjkm432!'),
        'connection_timeout': 10
    }
    
    connection = None
    try:
        print(f"Попытка подключения к {db_config['host']}:{db_config['port']}...")
        connection = mysql.connector.connect(**db_config)
        
        if connection.is_connected():
            print("✅ БД подключена")
            print()
            
            cursor = connection.cursor()
            
            # Подсчитываем дубликаты
            cursor.execute("""
                SELECT symbol, bot_name, side, entry_time, COUNT(*) as count
                FROM trades_history
                GROUP BY symbol, bot_name, side, entry_time
                HAVING count > 1
            """)
            duplicates = cursor.fetchall()
            
            if not duplicates:
                print("✅ Дубликатов не найдено")
                return
            
            print(f"📊 Найдено групп с дубликатами: {len(duplicates)}")
            total_duplicates = sum(row[4] - 1 for row in duplicates)
            print(f"📊 Всего дубликатов для удаления: {total_duplicates}")
            print()
            
            # Удаляем дубликаты, оставляя только запись с максимальным ID
            deleted_count = 0
            for row in duplicates:
                symbol, bot_name, side, entry_time, count = row
                # Удаляем все кроме одной (с максимальным ID)
                cursor.execute("""
                    DELETE FROM trades_history
                    WHERE symbol = %s
                    AND bot_name = %s
                    AND side = %s
                    AND entry_time = %s
                    AND id NOT IN (
                        SELECT id FROM (
                            SELECT MAX(id) as id
                            FROM trades_history
                            WHERE symbol = %s
                            AND bot_name = %s
                            AND side = %s
                            AND entry_time = %s
                        ) AS temp
                    )
                """, (symbol, bot_name, side, entry_time, symbol, bot_name, side, entry_time))
                deleted_count += cursor.rowcount
            
            connection.commit()
            
            print(f"✅ Удалено дубликатов: {deleted_count}")
            print()
            
            # Проверяем результат
            cursor.execute("SELECT COUNT(*) as count FROM trades_history")
            result = cursor.fetchone()
            remaining_count = result[0] if result else 0
            
            print(f"📊 Осталось записей в trades_history: {remaining_count}")
            print()
            
            # Проверяем, остались ли дубликаты
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM (
                    SELECT symbol, bot_name, side, entry_time, COUNT(*) as cnt
                    FROM trades_history
                    GROUP BY symbol, bot_name, side, entry_time
                    HAVING cnt > 1
                ) AS dup
            """)
            result = cursor.fetchone()
            remaining_duplicates = result[0] if result else 0
            
            if remaining_duplicates == 0:
                print("✅ Все дубликаты удалены!")
            else:
                print(f"⚠️  Осталось групп с дубликатами: {remaining_duplicates}")
            
            cursor.close()
            
    except Error as e:
        print(f"❌ Ошибка MySQL: {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if connection and connection.is_connected():
            connection.close()
            print("🔌 Соединение с БД закрыто")


if __name__ == "__main__":
    main()

