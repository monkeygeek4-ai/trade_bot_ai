#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к базе данных MySQL
"""
import sys
from services.db_service import DatabaseService


def main():
    print("=" * 50)
    print("Тест подключения к базе данных MySQL")
    print("=" * 50)
    print()
    
    # Создаем экземпляр сервиса
    db_service = DatabaseService()
    
    # Тестируем подключение
    print("Проверка подключения...")
    result = db_service.test_connection()
    
    print()
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"📊 Версия MySQL: {result.get('version', 'Unknown')}")
        print()
        
        # Получаем список таблиц
        print("Получение списка таблиц...")
        tables = db_service.get_tables()
        
        if tables:
            print(f"✅ Найдено таблиц: {len(tables)}")
            print()
            print("Список таблиц:")
            for i, table in enumerate(tables, 1):
                table_name = list(table.values())[0] if isinstance(table, dict) else table
                print(f"  {i}. {table_name}")
        else:
            print("⚠️  Таблицы не найдены или база данных пуста")
        
        # Тестируем простой запрос
        print()
        print("Тестирование простого запроса...")
        try:
            test_result = db_service.execute_query("SELECT 1 as test")
            if test_result:
                print("✅ Тестовый запрос выполнен успешно")
                print(f"   Результат: {test_result}")
        except Exception as e:
            print(f"❌ Ошибка при выполнении тестового запроса: {e}")
        
    else:
        print(f"❌ {result['message']}")
        sys.exit(1)
    
    # Закрываем подключение
    print()
    db_service.close()
    print()
    print("=" * 50)
    print("Тест завершен")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)

