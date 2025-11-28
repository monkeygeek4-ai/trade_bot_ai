#!/usr/bin/env python3
"""
Простой скрипт для очистки таблицы api_errors от всех ошибок
Без зависимостей от других модулей проекта
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 60)
    print("ОЧИСТКА ТАБЛИЦЫ api_errors")
    print("=" * 60)
    print()
    
    # Параметры подключения из переменных окружения
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
            
            # Подсчитываем количество записей
            cursor.execute("SELECT COUNT(*) as count FROM api_errors")
            result = cursor.fetchone()
            count_before = result[0] if result else 0
            
            print(f"📊 Найдено записей в api_errors: {count_before}")
            print()
            
            if count_before == 0:
                print("✅ Таблица уже пуста, нечего удалять")
                return
            
            # Удаляем все записи
            print(f"🗑️  Удаление {count_before} записей...")
            cursor.execute("DELETE FROM api_errors")
            deleted_count = cursor.rowcount
            connection.commit()
            
            print(f"✅ Удалено записей: {deleted_count}")
            print()
            
            # Проверяем результат
            cursor.execute("SELECT COUNT(*) as count FROM api_errors")
            result = cursor.fetchone()
            count_after = result[0] if result else 0
            
            print(f"📊 Осталось записей в api_errors: {count_after}")
            print()
            
            if count_after == 0:
                print("✅ Таблица успешно очищена!")
            else:
                print(f"⚠️  В таблице осталось {count_after} записей")
            
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

