#!/usr/bin/env python3
"""
Скрипт для удаления webhook и очистки обновлений
"""
import asyncio
from telegram import Bot
import config


async def clear_webhook():
    """Удалить webhook и очистить очередь обновлений"""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    
    try:
        # Получаем информацию о webhook
        webhook_info = await bot.get_webhook_info()
        print(f"Webhook URL: {webhook_info.url}")
        print(f"Pending updates: {webhook_info.pending_update_count}")
        
        # Удаляем webhook
        result = await bot.delete_webhook(drop_pending_updates=True)
        print(f"✅ Webhook удален: {result}")
        
        # Получаем информацию о боте
        bot_info = await bot.get_me()
        print(f"✅ Бот: @{bot_info.username}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(clear_webhook())

