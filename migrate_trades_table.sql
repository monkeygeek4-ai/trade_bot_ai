-- Миграция для добавления полей bot_name, stop_loss, take_profit в trades_history

ALTER TABLE trades_history 
ADD COLUMN IF NOT EXISTS bot_name VARCHAR(50) DEFAULT 'main' AFTER id;

ALTER TABLE trades_history 
ADD INDEX IF NOT EXISTS idx_bot_name (bot_name);

ALTER TABLE trades_history 
ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(20, 8) AFTER status;

ALTER TABLE trades_history 
ADD COLUMN IF NOT EXISTS take_profit DECIMAL(20, 8) AFTER stop_loss;

