import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Optional
import config
import numpy as np


class DatabaseService:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        """Подключение к базе данных"""
        try:
            print(f"Попытка подключения к {config.DB_HOST}:{config.DB_PORT}...")
            print(f"База данных: {config.DB_NAME}")
            print(f"Пользователь: {config.DB_USER}")
            
            self.connection = mysql.connector.connect(
                host=config.DB_HOST,
                port=int(config.DB_PORT),
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                connection_timeout=10
            )
            if self.connection.is_connected():
                db_info = self.connection.get_server_info()
                print(f"✅ Успешное подключение к базе данных MySQL")
                print(f"   Версия сервера: {db_info}")
                return True
        except Error as e:
            error_msg = str(e)
            print(f"❌ Ошибка при подключении к MySQL: {error_msg}")
            
            # Детальная диагностика
            if "Access denied" in error_msg:
                print("\n💡 Возможные причины:")
                print("   - Неверный пароль или имя пользователя")
                print("   - IP адрес не разрешен для доступа к БД")
                print("   - Специальные символы в пароле требуют экранирования")
            elif "Can't connect" in error_msg:
                print("\n💡 Возможные причины:")
                print("   - Сервер БД недоступен")
                print("   - Неверный хост или порт")
                print("   - Проблемы с сетью")
            
            return False
    
    def test_connection(self):
        """Тест подключения к базе данных"""
        cursor = None
        try:
            if self.connection and self.connection.is_connected():
                cursor = self.connection.cursor(buffered=True)
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                cursor.close()
                return {
                    "success": True,
                    "message": "Подключение успешно",
                    "version": version[0] if version else "Unknown"
                }
            else:
                return {
                    "success": False,
                    "message": "Нет активного подключения"
                }
        except Error as e:
            if cursor:
                cursor.close()
            return {
                "success": False,
                "message": f"Ошибка: {str(e)}"
            }
    
    def execute_query(self, query, params=None):
        """Выполнить SQL запрос"""
        cursor = None
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
            
            cursor = self.connection.cursor(dictionary=True, buffered=True)
            cursor.execute(query, params or ())
            
            if query.strip().upper().startswith('SELECT') or query.strip().upper().startswith('SHOW'):
                result = cursor.fetchall()
            else:
                self.connection.commit()
                result = cursor.rowcount
            
            cursor.close()
            return result
        except Error as e:
            if cursor:
                cursor.close()
            print(f"Ошибка при выполнении запроса: {e}")
            return None
    
    def get_tables(self):
        """Получить список таблиц в базе данных"""
        try:
            query = "SHOW TABLES"
            result = self.execute_query(query)
            return result
        except Error as e:
            print(f"Ошибка при получении списка таблиц: {e}")
            return []
    
    def close(self):
        """Закрыть подключение"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("✅ Подключение к MySQL закрыто")
    
    def init_tables(self):
        """Инициализировать таблицы для хранения исторических данных"""
        try:
            # Таблица для хранения исторических данных по монетам
            create_market_history_table = """
            CREATE TABLE IF NOT EXISTS market_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timestamp DATETIME NOT NULL,
                hour_utc INT NOT NULL,
                price DECIMAL(20, 8) NOT NULL,
                volume_24h DECIMAL(20, 2),
                volatility DECIMAL(10, 4),
                funding_rate DECIMAL(10, 8),
                open_interest DECIMAL(20, 2),
                rsi DECIMAL(6, 2),
                atr DECIMAL(20, 8),
                macd DECIMAL(20, 8),
                macd_signal DECIMAL(20, 8),
                bb_upper DECIMAL(20, 8),
                bb_middle DECIMAL(20, 8),
                bb_lower DECIMAL(20, 8),
                ema_50 DECIMAL(20, 8),
                ema_200 DECIMAL(20, 8),
                vwap DECIMAL(20, 8),
                liquidity_score DECIMAL(6, 2),
                INDEX idx_symbol_timestamp (symbol, timestamp),
                INDEX idx_hour_utc (hour_utc),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            # Таблица для статистики по времени суток
            create_time_stats_table = """
            CREATE TABLE IF NOT EXISTS time_of_day_stats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                hour_utc INT NOT NULL,
                avg_volatility DECIMAL(10, 4),
                avg_volume DECIMAL(20, 2),
                avg_spread DECIMAL(10, 8),
                trade_count INT DEFAULT 0,
                win_rate DECIMAL(5, 2),
                avg_pnl DECIMAL(10, 4),
                last_updated DATETIME NOT NULL,
                UNIQUE KEY unique_symbol_hour (symbol, hour_utc),
                INDEX idx_hour_utc (hour_utc)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            # Таблица для хранения результатов сделок
            create_trades_table = """
            CREATE TABLE IF NOT EXISTS trades_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                bot_name VARCHAR(50) DEFAULT 'main',
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                entry_time DATETIME NOT NULL,
                exit_time DATETIME,
                entry_price DECIMAL(20, 8) NOT NULL,
                exit_price DECIMAL(20, 8),
                quantity DECIMAL(20, 8) NOT NULL,
                pnl DECIMAL(20, 8),
                pnl_percent DECIMAL(10, 4),
                hour_utc INT NOT NULL,
                leverage INT,
                status VARCHAR(20) DEFAULT 'open',
                stop_loss DECIMAL(20, 8),
                take_profit DECIMAL(20, 8),
                INDEX idx_symbol (symbol),
                INDEX idx_entry_time (entry_time),
                INDEX idx_hour_utc (hour_utc),
                INDEX idx_status (status),
                INDEX idx_bot_name (bot_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            # Миграция: добавляем поля bot_name, stop_loss, take_profit если их нет
            try:
                import logging
                logger = logging.getLogger(__name__)
                cursor = self.connection.cursor()
                cursor.execute("SHOW COLUMNS FROM trades_history LIKE 'bot_name'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE trades_history ADD COLUMN bot_name VARCHAR(50) DEFAULT 'main' AFTER id")
                    cursor.execute("ALTER TABLE trades_history ADD INDEX idx_bot_name (bot_name)")
                    logger.info("✅ Добавлено поле bot_name в trades_history")
                
                cursor.execute("SHOW COLUMNS FROM trades_history LIKE 'stop_loss'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE trades_history ADD COLUMN stop_loss DECIMAL(20, 8) AFTER status")
                    logger.info("✅ Добавлено поле stop_loss в trades_history")
                
                cursor.execute("SHOW COLUMNS FROM trades_history LIKE 'take_profit'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE trades_history ADD COLUMN take_profit DECIMAL(20, 8) AFTER stop_loss")
                    logger.info("✅ Добавлено поле take_profit в trades_history")
                
                self.connection.commit()
                cursor.close()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Миграция trades_history: {e}")
                if self.connection:
                    self.connection.rollback()
            
            # Обновляем таблицу ai_responses (добавляем недостающие колонки)
            try:
                import logging
                cursor = self.connection.cursor()
                cursor.execute("SHOW COLUMNS FROM ai_responses LIKE 'prompt'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE ai_responses ADD COLUMN prompt LONGTEXT AFTER symbols")
                    logger = logging.getLogger(__name__)
                    logger.info("✅ Добавлено поле prompt в ai_responses")
                cursor.close()
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Миграция ai_responses: {e}")
                if self.connection:
                    self.connection.rollback()
            
            # Таблица для хранения AI ответов и рекомендаций
            create_ai_responses_table = """
            CREATE TABLE IF NOT EXISTS ai_responses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                request_type VARCHAR(50) NOT NULL,
                symbols TEXT,
                prompt LONGTEXT,
                recommended_symbol VARCHAR(20),
                recommended_side VARCHAR(10),
                entry_price DECIMAL(20, 8),
                stop_loss DECIMAL(20, 8),
                take_profit DECIMAL(20, 8),
                confidence DECIMAL(5, 2),
                reasoning TEXT,
                full_response TEXT,
                tokens_used INT,
                response_time_ms INT,
                INDEX idx_timestamp (timestamp),
                INDEX idx_recommended_symbol (recommended_symbol),
                INDEX idx_request_type (request_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            # Таблица для хранения ошибок API
            create_api_errors_table = """
            CREATE TABLE IF NOT EXISTS api_errors (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                api_method VARCHAR(50) NOT NULL,
                symbol VARCHAR(20),
                error_code VARCHAR(20),
                error_message TEXT,
                response_data TEXT,
                INDEX idx_timestamp (timestamp),
                INDEX idx_api_method (api_method),
                INDEX idx_symbol (symbol)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            # Таблица для кэширования данных по монетам (быстрый доступ)
            create_market_cache_table = """
            CREATE TABLE IF NOT EXISTS market_cache (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timestamp DATETIME NOT NULL,
                data_type VARCHAR(50) NOT NULL,
                data_json TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                UNIQUE KEY unique_symbol_type (symbol, data_type),
                INDEX idx_expires_at (expires_at),
                INDEX idx_symbol_timestamp (symbol, timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            self.execute_query(create_market_history_table)
            self.execute_query(create_time_stats_table)
            self.execute_query(create_trades_table)
            self.execute_query(create_ai_responses_table)
            self.execute_query(create_api_errors_table)
            self.execute_query(create_market_cache_table)
            
            return True
        except Error as e:
            print(f"Ошибка при инициализации таблиц: {e}")
            return False
    
    def _validate_market_data(self, market_data: Dict, historical_data: Dict) -> bool:
        """Валидация данных перед сохранением"""
        try:
            # Проверяем обязательные поля
            if not market_data.get('current_price') or market_data.get('current_price', 0) <= 0:
                return False
            
            # Проверяем разумность значений
            price = market_data.get('current_price', 0)
            if price < 0.0001 or price > 100000000:  # Разумные границы для крипто
                return False
            
            volatility = market_data.get('volatility', 0)
            if volatility < 0 or volatility > 100:  # Волатильность не может быть > 100%
                return False
            
            return True
        except Exception:
            return False
    
    def save_market_snapshot(self, symbol: str, market_data: Dict, historical_data: Dict):
        """Сохранить снимок рыночных данных с валидацией"""
        try:
            # Валидация данных перед сохранением
            if not self._validate_market_data(market_data, historical_data):
                print(f"⚠️ Данные для {symbol} не прошли валидацию, пропускаем сохранение")
                return False
            
            from datetime import datetime
            
            timestamp = datetime.utcnow()
            hour_utc = timestamp.hour
            
            historical = historical_data or {}
            macd_data = historical.get('macd', {})
            bb_data = historical.get('bollinger_bands', {})
            
            query = """
            INSERT INTO market_history (
                symbol, timestamp, hour_utc, price, volume_24h, volatility,
                funding_rate, open_interest, rsi, atr, macd, macd_signal,
                bb_upper, bb_middle, bb_lower, ema_50, ema_200, vwap, liquidity_score
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            params = (
                symbol,
                timestamp,
                hour_utc,
                market_data.get('current_price', 0),
                market_data.get('volume_24h', 0),
                market_data.get('volatility', 0),
                market_data.get('funding_rate', 0),
                market_data.get('open_interest', 0),
                historical.get('rsi'),
                historical.get('atr'),
                macd_data.get('macd') if macd_data else None,
                macd_data.get('signal') if macd_data else None,
                bb_data.get('upper_band') if bb_data else None,
                bb_data.get('middle_band') if bb_data else None,
                bb_data.get('lower_band') if bb_data else None,
                historical.get('ema_50'),
                historical.get('ema_200'),
                historical.get('vwap'),
                market_data.get('liquidity_score', 0)
            )
            
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при сохранении снимка рынка: {e}")
            # Сохраняем ошибку в таблицу api_errors
            try:
                self.save_api_error("save_market_snapshot", symbol, "DB_ERROR", str(e))
            except:
                pass
            return False
    
    def get_time_of_day_stats(self, symbol: str = None, hours: List[int] = None) -> Dict:
        """Получить статистику по времени суток"""
        try:
            from datetime import datetime, timedelta
            
            # Берем данные за последние 30 дней
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            conditions = ["timestamp >= %s"]
            params = [cutoff_date]
            
            if symbol:
                conditions.append("symbol = %s")
                params.append(symbol)
            
            if hours:
                placeholders = ','.join(['%s'] * len(hours))
                conditions.append(f"hour_utc IN ({placeholders})")
                params.extend(hours)
            
            where_clause = " AND ".join(conditions)
            
            query = f"""
            SELECT 
                hour_utc,
                AVG(volatility) as avg_volatility,
                AVG(volume_24h) as avg_volume,
                AVG(ABS(funding_rate)) as avg_funding_rate,
                COUNT(*) as data_points
            FROM market_history
            WHERE {where_clause}
            GROUP BY hour_utc
            ORDER BY hour_utc
            """
            
            result = self.execute_query(query, params)
            
            if not result:
                return {}
            
            stats = {}
            for row in result:
                hour = row['hour_utc']
                stats[hour] = {
                    'avg_volatility': float(row['avg_volatility'] or 0),
                    'avg_volume': float(row['avg_volume'] or 0),
                    'avg_funding_rate': float(row['avg_funding_rate'] or 0),
                    'data_points': row['data_points']
                }
            
            return stats
        except Error as e:
            print(f"Ошибка при получении статистики по времени: {e}")
            return {}
    
    def get_liquidity_period_analysis(self, symbol: str = None) -> Dict:
        """Анализ ликвидности по периодам суток"""
        try:
            stats = self.get_time_of_day_stats(symbol)
            
            if not stats:
                return {
                    'low_liquidity': [0, 1, 2, 3],
                    'high_liquidity': list(range(8, 20)),
                    'moderate_liquidity': list(range(4, 8)) + list(range(20, 24))
                }
            
            # Анализируем средние объемы по часам
            hour_volumes = {hour: data['avg_volume'] for hour, data in stats.items()}
            
            if not hour_volumes:
                return {
                    'low_liquidity': [0, 1, 2, 3],
                    'high_liquidity': list(range(8, 20)),
                    'moderate_liquidity': list(range(4, 8)) + list(range(20, 24))
                }
            
            max_volume = max(hour_volumes.values())
            min_volume = min(hour_volumes.values())
            threshold_low = min_volume + (max_volume - min_volume) * 0.3
            threshold_high = min_volume + (max_volume - min_volume) * 0.7
            
            low_liquidity = [h for h, vol in hour_volumes.items() if vol < threshold_low]
            high_liquidity = [h for h, vol in hour_volumes.items() if vol >= threshold_high]
            moderate_liquidity = [h for h in range(24) if h not in low_liquidity and h not in high_liquidity]
            
            return {
                'low_liquidity': sorted(low_liquidity),
                'high_liquidity': sorted(high_liquidity),
                'moderate_liquidity': sorted(moderate_liquidity),
                'stats': stats
            }
        except Exception as e:
            print(f"Ошибка при анализе ликвидности: {e}")
            return {
                'low_liquidity': [0, 1, 2, 3],
                'high_liquidity': list(range(8, 20)),
                'moderate_liquidity': list(range(4, 8)) + list(range(20, 24))
            }
    
    def save_ai_response(self, request_type: str, symbols: List[str], response_data: Dict, 
                        prompt_text: str = None, tokens_used: int = None, response_time_ms: int = None):
        """Сохранить ответ AI для анализа"""
        try:
            from datetime import datetime
            import json
            
            timestamp = datetime.utcnow()
            
            query = """
            INSERT INTO ai_responses (
                timestamp, request_type, symbols, prompt, recommended_symbol, recommended_side,
                entry_price, stop_loss, take_profit, confidence, reasoning, full_response,
                tokens_used, response_time_ms
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            params = (
                timestamp,
                request_type,
                ','.join(symbols) if symbols else None,
                prompt_text,
                response_data.get('recommended_symbol'),
                response_data.get('recommended_side'),
                response_data.get('entry_price'),
                response_data.get('stop_loss'),
                response_data.get('take_profit'),
                response_data.get('confidence'),
                response_data.get('reasoning'),
                json.dumps(response_data) if response_data else None,
                tokens_used,
                response_time_ms
            )
            
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при сохранении ответа AI: {e}")
            return False
    
    def save_api_error(self, api_method: str, symbol: str, error_code: str, 
                      error_message: str, response_data: Dict = None):
        """Сохранить ошибку API для анализа"""
        try:
            from datetime import datetime
            import json
            
            timestamp = datetime.utcnow()
            
            query = """
            INSERT INTO api_errors (
                timestamp, api_method, symbol, error_code, error_message, response_data
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            """
            
            params = (
                timestamp,
                api_method,
                symbol,
                error_code,
                error_message,
                json.dumps(response_data) if response_data else None
            )
            
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при сохранении ошибки API: {e}")
            return False
    
    def save_to_cache(self, symbol: str, data_type: str, data: Dict, ttl_minutes: int = 5):
        """Сохранить данные в кэш"""
        try:
            from datetime import datetime, timedelta
            import json
            
            timestamp = datetime.utcnow()
            expires_at = timestamp + timedelta(minutes=ttl_minutes)
            
            query = """
            INSERT INTO market_cache (symbol, timestamp, data_type, data_json, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                timestamp = VALUES(timestamp),
                data_json = VALUES(data_json),
                expires_at = VALUES(expires_at)
            """
            
            params = (
                symbol,
                timestamp,
                data_type,
                json.dumps(data),
                expires_at
            )
            
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при сохранении в кэш: {e}")
            return False
    
    def get_from_cache(self, symbol: str, data_type: str) -> Optional[Dict]:
        """Получить данные из кэша"""
        try:
            from datetime import datetime
            import json
            
            query = """
            SELECT data_json, expires_at
            FROM market_cache
            WHERE symbol = %s AND data_type = %s AND expires_at > %s
            ORDER BY timestamp DESC
            LIMIT 1
            """
            
            params = (symbol, data_type, datetime.utcnow())
            result = self.execute_query(query, params)
            
            if result and len(result) > 0:
                return json.loads(result[0]['data_json'])
            
            return None
        except Error as e:
            print(f"Ошибка при получении из кэша: {e}")
            return None
    
    def cleanup_expired_cache(self):
        """Очистить истекший кэш"""
        try:
            from datetime import datetime
            
            query = "DELETE FROM market_cache WHERE expires_at < %s"
            params = (datetime.utcnow(),)
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при очистке кэша: {e}")
            return False
    
    def calculate_correlation(self, symbol1: str, symbol2: str, days: int = 30) -> float:
        """
        Рассчитать корреляцию между двумя символами на основе исторических данных
        
        Args:
            symbol1: Первый символ
            symbol2: Второй символ
            days: Количество дней для расчета (по умолчанию 30)
        
        Returns:
            Коэффициент корреляции от -1 до 1 (0 если данных недостаточно)
        """
        try:
            from datetime import datetime, timedelta
            import numpy as np
            
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            
            # Получаем исторические цены для обоих символов
            query = """
            SELECT timestamp, price 
            FROM market_history
            WHERE symbol = %s AND timestamp >= %s
            ORDER BY timestamp ASC
            """
            
            prices1 = self.execute_query(query, (symbol1, cutoff_time))
            prices2 = self.execute_query(query, (symbol2, cutoff_time))
            
            if not prices1 or not prices2 or len(prices1) < 10 or len(prices2) < 10:
                return 0.0
            
            # Создаем словари для синхронизации по времени
            prices1_dict = {row['timestamp']: float(row['price']) for row in prices1}
            prices2_dict = {row['timestamp']: float(row['price']) for row in prices2}
            
            # Находим общие временные точки
            common_timestamps = set(prices1_dict.keys()) & set(prices2_dict.keys())
            if len(common_timestamps) < 10:
                return 0.0
            
            # Сортируем по времени
            sorted_timestamps = sorted(common_timestamps)
            
            # Вычисляем процентные изменения цен
            returns1 = []
            returns2 = []
            
            for i in range(1, len(sorted_timestamps)):
                price1_prev = prices1_dict[sorted_timestamps[i-1]]
                price1_curr = prices1_dict[sorted_timestamps[i]]
                price2_prev = prices2_dict[sorted_timestamps[i-1]]
                price2_curr = prices2_dict[sorted_timestamps[i]]
                
                if price1_prev > 0 and price2_prev > 0:
                    ret1 = (price1_curr - price1_prev) / price1_prev
                    ret2 = (price2_curr - price2_prev) / price2_prev
                    returns1.append(ret1)
                    returns2.append(ret2)
            
            if len(returns1) < 10:
                return 0.0
            
            # Рассчитываем корреляцию Пирсона
            correlation = np.corrcoef(returns1, returns2)[0, 1]
            
            # Обрабатываем NaN
            if np.isnan(correlation):
                return 0.0
            
            return float(correlation)
            
        except Exception as e:
            print(f"Ошибка при расчете корреляции между {symbol1} и {symbol2}: {e}")
            return 0.0
    
    def rotate_old_data(self, table_name: str, keep_days: int = 90):
        """
        Удалить старые данные из таблицы, оставив только последние N дней
        
        Args:
            table_name: Имя таблицы
            keep_days: Количество дней для хранения (по умолчанию 90)
        
        Returns:
            Количество удаленных записей
        """
        try:
            from datetime import datetime, timedelta
            
            cutoff_time = datetime.utcnow() - timedelta(days=keep_days)
            
            # Проверяем, что таблица существует
            valid_tables = ['market_history', 'ai_responses', 'api_errors', 'trades_history']
            if table_name not in valid_tables:
                print(f"⚠️ Таблица {table_name} не в списке разрешенных для ротации")
                return 0
            
            query = f"DELETE FROM {table_name} WHERE timestamp < %s"
            params = (cutoff_time,)
            
            result = self.execute_query(query, params)
            
            if result:
                print(f"✅ Удалено {result} записей из {table_name} старше {keep_days} дней")
                return result
            else:
                return 0
                
        except Exception as e:
            print(f"Ошибка при ротации данных в {table_name}: {e}")
            return 0
    
    def cleanup_old_ai_responses(self, keep_count: int = 1000):
        """
        Удалить старые AI ответы, оставив только последние N записей
        
        Args:
            keep_count: Количество записей для хранения (по умолчанию 1000)
        
        Returns:
            Количество удаленных записей
        """
        try:
            # Получаем ID последних N записей
            query = """
            SELECT id FROM ai_responses
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            keep_ids = self.execute_query(query, (keep_count,))
            
            if not keep_ids or len(keep_ids) == 0:
                return 0
            
            keep_ids_list = [row['id'] for row in keep_ids]
            placeholders = ','.join(['%s'] * len(keep_ids_list))
            
            # Удаляем все остальные
            delete_query = f"DELETE FROM ai_responses WHERE id NOT IN ({placeholders})"
            result = self.execute_query(delete_query, tuple(keep_ids_list))
            
            if result:
                print(f"✅ Удалено {result} старых AI ответов, оставлено {len(keep_ids_list)}")
                return result
            else:
                return 0
                
        except Exception as e:
            print(f"Ошибка при очистке старых AI ответов: {e}")
            return 0
    
    def save_trade(self, symbol: str, side: str, entry_price: float, quantity: float,
                   leverage: int, stop_loss: float = None, take_profit: float = None,
                   bot_name: str = "main", status: str = "open"):
        """
        Сохранить сделку в БД
        
        Args:
            symbol: Символ торговой пары
            side: Сторона сделки (Long/Short)
            entry_price: Цена входа
            quantity: Количество
            leverage: Плечо
            stop_loss: Стоп-лосс
            take_profit: Тейк-профит
            bot_name: Имя бота (main/iliya)
            status: Статус (open/closed)
        
        Returns:
            ID сохраненной сделки или None
        """
        try:
            from datetime import datetime
            
            entry_time = datetime.utcnow()
            hour_utc = entry_time.hour
            
            # Проверяем наличие колонок
            columns = self.execute_query("SHOW COLUMNS FROM trades_history")
            column_names = [col['Field'] for col in columns] if columns else []
            has_bot_name = 'bot_name' in column_names
            has_stop_loss = 'stop_loss' in column_names
            has_take_profit = 'take_profit' in column_names
            
            # Формируем запрос в зависимости от наличия колонок
            fields = ['symbol', 'side', 'entry_time', 'entry_price', 'quantity', 'leverage', 'hour_utc', 'status']
            values = [symbol.upper(), side, entry_time, entry_price, quantity, leverage, hour_utc, status]
            
            if has_bot_name:
                fields.insert(0, 'bot_name')
                values.insert(0, bot_name)
            
            if has_stop_loss:
                fields.append('stop_loss')
                values.append(stop_loss)
            
            if has_take_profit:
                fields.append('take_profit')
                values.append(take_profit)
            
            placeholders = ', '.join(['%s'] * len(fields))
            fields_str = ', '.join(fields)
            
            query = f"""
            INSERT INTO trades_history ({fields_str})
            VALUES ({placeholders})
            """
            
            params = tuple(values)
            
            result = self.execute_query(query, params)
            return result
        except Error as e:
            print(f"Ошибка при сохранении сделки: {e}")
            return None
    
    def update_trade_exit(self, symbol: str, exit_price: float, pnl: float,
                          pnl_percent: float, bot_name: str = "main"):
        """
        Обновить сделку при выходе
        
        Args:
            symbol: Символ торговой пары
            exit_price: Цена выхода
            pnl: P&L в USDT
            pnl_percent: P&L в процентах
            bot_name: Имя бота
        
        Returns:
            True если успешно
        """
        try:
            from datetime import datetime
            
            exit_time = datetime.utcnow()
            
            # Проверяем наличие колонки bot_name
            check_column = self.execute_query("SHOW COLUMNS FROM trades_history LIKE 'bot_name'")
            has_bot_name = check_column and len(check_column) > 0
            
            if has_bot_name:
                # Обновляем самую последнюю открытую сделку или последнюю сделку без exit_time
                query = """
                UPDATE trades_history
                SET exit_time = %s, exit_price = %s, pnl = %s, pnl_percent = %s, status = 'closed'
                WHERE symbol = %s AND bot_name = %s AND (status = 'open' OR exit_time IS NULL)
                ORDER BY entry_time DESC
                LIMIT 1
                """
                params = (exit_time, exit_price, pnl, pnl_percent, symbol.upper(), bot_name)
            else:
                query = """
                UPDATE trades_history
                SET exit_time = %s, exit_price = %s, pnl = %s, pnl_percent = %s, status = 'closed'
                WHERE symbol = %s AND status = 'open'
                ORDER BY entry_time DESC
                LIMIT 1
                """
                params = (exit_time, exit_price, pnl, pnl_percent, symbol.upper())
            
            self.execute_query(query, params)
            return True
        except Error as e:
            print(f"Ошибка при обновлении сделки: {e}")
            return False
    
    def get_latest_market_data(self, symbol: str, minutes_back: int = 5) -> Optional[Dict]:
        """Получить последние данные из БД (вместо запроса к API)"""
        try:
            from datetime import datetime, timedelta
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_back)
            
            query = """
            SELECT * FROM market_history
            WHERE symbol = %s AND timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT 1
            """
            
            params = (symbol, cutoff_time)
            result = self.execute_query(query, params)
            
            if result and len(result) > 0:
                row = result[0]
                return {
                    "symbol": row["symbol"],
                    "price": float(row["price"]),
                    "volume_24h": float(row["volume_24h"] or 0),
                    "volatility": float(row["volatility"] or 0),
                    "funding_rate": float(row["funding_rate"] or 0),
                    "open_interest": float(row["open_interest"] or 0),
                    "rsi": float(row["rsi"]) if row["rsi"] else None,
                    "atr": float(row["atr"]) if row["atr"] else None,
                    "macd": float(row["macd"]) if row["macd"] else None,
                    "macd_signal": float(row["macd_signal"]) if row["macd_signal"] else None,
                    "bb_upper": float(row["bb_upper"]) if row["bb_upper"] else None,
                    "bb_middle": float(row["bb_middle"]) if row["bb_middle"] else None,
                    "bb_lower": float(row["bb_lower"]) if row["bb_lower"] else None,
                    "ema_50": float(row["ema_50"]) if row["ema_50"] else None,
                    "ema_200": float(row["ema_200"]) if row["ema_200"] else None,
                    "vwap": float(row["vwap"]) if row["vwap"] else None,
                    "liquidity_score": float(row["liquidity_score"] or 0),
                    "timestamp": row["timestamp"]
                }
            
            return None
        except Error as e:
            print(f"Ошибка при получении данных из БД: {e}")
            return None

