#!/usr/bin/env python3
"""
Скрипт для очистки старых сделок из таблицы trades_history
Оставляет только сделки за последние 30 дней
"""
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 60)
    print("ОЧИСТКА СТАРЫХ СДЕЛОК ИЗ trades_history")
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
            
            # Подсчитываем общее количество записей
            cursor.execute("SELECT COUNT(*) as count FROM trades_history")
            result = cursor.fetchone()
            total_count = result[0] if result else 0
            print(f"📊 Всего записей в trades_history: {total_count}")
            
            # Подсчитываем количество старых записей (старше 30 дней)
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM trades_history 
                WHERE entry_time < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            result = cursor.fetchone()
            old_count = result[0] if result else 0
            print(f"📊 Записей старше 30 дней: {old_count}")
            
            # Подсчитываем количество записей за последние 30 дней
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM trades_history 
                WHERE entry_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            result = cursor.fetchone()
            recent_count = result[0] if result else 0
            print(f"📊 Записей за последние 30 дней: {recent_count}")
            print()
            
            if old_count == 0:
                print("✅ Старых записей нет, нечего удалять")
                return
            
            # Удаляем старые записи
            print(f"🗑️  Удаление {old_count} старых записей...")
            cursor.execute("""
                DELETE FROM trades_history 
                WHERE entry_time < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            deleted_count = cursor.rowcount
            connection.commit()
            
            print(f"✅ Удалено записей: {deleted_count}")
            print()
            
            # Проверяем результат
            cursor.execute("SELECT COUNT(*) as count FROM trades_history")
            result = cursor.fetchone()
            remaining_count = result[0] if result else 0
            
            print(f"📊 Осталось записей в trades_history: {remaining_count}")
            print()
            
            if remaining_count == recent_count:
                print("✅ Очистка выполнена успешно!")
                print(f"   Осталось только записи за последние 30 дней: {remaining_count}")
            else:
                print(f"⚠️  Несоответствие: ожидалось {recent_count}, осталось {remaining_count}")
            
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

