#!/usr/bin/env python3
"""
Простой тест для проверки работы бота
"""
import asyncio
from telegram import Bot
import config


async def test_bot():
    """Тест отправки сообщения боту"""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    
    # Получаем информацию о боте
    try:
        bot_info = await bot.get_me()
        print(f"✅ Бот подключен: @{bot_info.username}")
        print(f"   ID: {bot_info.id}")
        print(f"   Имя: {bot_info.first_name}")
        print()
        
        # Проверяем, можем ли отправить сообщение
        if config.TELEGRAM_CHAT_ID:
            try:
                await bot.send_message(
                    chat_id=config.TELEGRAM_CHAT_ID,
                    text="🧪 Тестовое сообщение от бота. Если вы видите это, бот работает!"
                )
                print(f"✅ Тестовое сообщение отправлено в чат {config.TELEGRAM_CHAT_ID}")
            except Exception as e:
                print(f"❌ Ошибка при отправке сообщения: {e}")
        else:
            print("⚠️  TELEGRAM_CHAT_ID не установлен, пропускаем тест отправки")
        
    except Exception as e:
        print(f"❌ Ошибка при подключении к боту: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_bot())

