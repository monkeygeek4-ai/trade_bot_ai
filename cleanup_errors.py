#!/usr/bin/env python3
"""
Скрипт для очистки таблицы api_errors от всех ошибок
"""
import sys
from services.db_service import DatabaseService


def main():
    print("=" * 60)
    print("ОЧИСТКА ТАБЛИЦЫ api_errors")
    print("=" * 60)
    print()
    
    # Инициализация сервиса БД
    try:
        db_service = DatabaseService()
        if not db_service.connection or not db_service.connection.is_connected():
            print("❌ Не удалось подключиться к БД")
            sys.exit(1)
        
        print("✅ БД подключена")
        print()
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        sys.exit(1)
    
    # Подсчитываем количество записей перед удалением
    try:
        cursor = db_service.connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM api_errors")
        result = cursor.fetchone()
        count_before = result[0] if result else 0
        cursor.close()
        
        print(f"📊 Найдено записей в api_errors: {count_before}")
        print()
        
        if count_before == 0:
            print("✅ Таблица уже пуста, нечего удалять")
            sys.exit(0)
        
        # Подтверждение
        print(f"⚠️  Будет удалено {count_before} записей из таблицы api_errors")
        print("   Продолжить? (yes/no): ", end="")
        
        # Для автоматического выполнения используем yes
        confirm = "yes"  # Можно изменить на input() для интерактивного режима
        
        if confirm.lower() != "yes":
            print("❌ Операция отменена")
            sys.exit(0)
        
        print()
        print("🗑️  Удаление записей...")
        
        # Удаляем все записи
        cursor = db_service.connection.cursor()
        cursor.execute("DELETE FROM api_errors")
        deleted_count = cursor.rowcount
        db_service.connection.commit()
        cursor.close()
        
        print(f"✅ Удалено записей: {deleted_count}")
        print()
        
        # Проверяем результат
        cursor = db_service.connection.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM api_errors")
        result = cursor.fetchone()
        count_after = result[0] if result else 0
        cursor.close()
        
        print(f"📊 Осталось записей в api_errors: {count_after}")
        print()
        
        if count_after == 0:
            print("✅ Таблица успешно очищена!")
        else:
            print(f"⚠️  В таблице осталось {count_after} записей")
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        sys.exit(1)
    finally:
        if db_service.connection and db_service.connection.is_connected():
            db_service.connection.close()
            print("🔌 Соединение с БД закрыто")


if __name__ == "__main__":
    main()

