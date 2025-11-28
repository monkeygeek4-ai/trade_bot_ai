#!/usr/bin/env python3
"""
Скрипт для получения Chat ID из Telegram
"""
import asyncio
from telegram import Bot
import config


async def get_chat_id():
    """Получить Chat ID из последних обновлений"""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    
    try:
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
        print()
        
        # Получаем последние обновления
        updates = await bot.get_updates(limit=10)
        
        if not updates:
            print("❌ Нет обновлений. Отправьте боту любое сообщение и попробуйте снова.")
            print()
            print("Или используйте команду в Telegram:")
            print("  /start")
            return
        
        print("📋 Найденные Chat ID:")
        print("-" * 50)
        
        chat_ids = set()
        for update in updates:
            if update.message:
                chat = update.message.chat
                chat_ids.add(chat.id)
                print(f"Chat ID: {chat.id}")
                print(f"  Тип: {chat.type}")
                if chat.first_name:
                    print(f"  Имя: {chat.first_name}")
                if chat.username:
                    print(f"  Username: @{chat.username}")
                print()
        
        if chat_ids:
            print("=" * 50)
            print("✅ Ваш Chat ID (добавьте в .env):")
            print(f"TELEGRAM_CHAT_ID={list(chat_ids)[0]}")
            print("=" * 50)
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(get_chat_id())

