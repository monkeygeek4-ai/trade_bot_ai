"""
Сервис для глубокого анализа рынка популярных криптовалют
Включает: исторический анализ, адаптивное leverage, рекомендации
"""
import logging
from services.bybit_service import BybitService
from services.risk_management_service import RiskManagementService
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from statistics import mean
import config

logger = logging.getLogger(__name__)


class MarketAnalysisService:
    def __init__(self, news_service=None, db_service=None):
        self.bybit_service = BybitService(db_service=db_service)  # Передаем db_service для сохранения ошибок
        self.risk_service = RiskManagementService()
        self.news_service = news_service  # Опционально, для интеграции новостей
        self.db_service = db_service  # Опционально, для сохранения истории
        
        # Популярные монеты для анализа (топ по объему и ликвидности)
        # Только символы, доступные на Bybit для фьючерсов (linear)
        # SHIBUSDT и PEPEUSDT недоступны для фьючерсов - убраны
        self.popular_coins = [
            "BTCUSDT",   # Bitcoin
            "ETHUSDT",   # Ethereum
            "SOLUSDT",   # Solana
            "BNBUSDT",   # Binance Coin
            "XRPUSDT",   # Ripple
            "ADAUSDT",   # Cardano
            "DOGEUSDT",  # Dogecoin
            "AVAXUSDT",  # Avalanche
            "MATICUSDT", # Polygon (старый тикер, но все еще работает)
            "LINKUSDT",  # Chainlink
            "TONUSDT",   # Toncoin
            "TRXUSDT",   # Tron
            "LTCUSDT",   # Litecoin
            "NEARUSDT",  # NEAR
            "APTUSDT",   # Aptos
            "OPUSDT",    # Optimism
            "ARBUSDT",   # Arbitrum
            "POLUSDT",   # Polygon (новый тикер)
            "SEIUSDT",   # SEI
            "SUIUSDT",   # Sui
        ]
        
        # Параметры для безопасной торговли с 100$
        self.capital = 100.0  # Стартовый капитал (виртуальный, для расчёта)
        self.daily_target = 7.5  # Средняя цель: 7.5$ в день (5-10$ диапазон)
        # Максимальный риск в день/на сделку: читаем из config.AUTO_RISK_PER_TRADE (по умолчанию 2%)
        self.max_daily_risk = getattr(config, "AUTO_RISK_PER_TRADE", 0.02)
        self.min_risk_reward = 2.0  # Минимальный risk-reward для безопасной торговли: 1:2
    
    def get_historical_data(self, symbol: str, days: int = 7) -> Optional[Dict]:
        """
        Получить исторические данные за период
        
        Args:
            symbol: Символ для анализа
            days: Количество дней истории
        
        Returns:
            Словарь с историческими данными
        """
        try:
            # ВРЕМЕННО: Берем все данные напрямую из API, пока база наполняется
            # Не используем кэш БД, чтобы избежать неполных/неправильных данных
            logger.info(f"📡 Получение данных для {symbol} напрямую из Bybit API (БД временно отключена)")
            
            # Всегда запрашиваем данные напрямую из API
            ticker = self.bybit_service.get_ticker(symbol)
            if not ticker:
                logger.warning(f"Не удалось получить ticker для {symbol}")
                return None

            funding = self.bybit_service.get_funding_rate(symbol)
            oi = self.bybit_service.get_open_interest(symbol)
            candles = self.bybit_service.get_kline(symbol=symbol, interval="60", limit=240)
            candle_stats = self._analyze_candles(candles)
            whale_activity = self._get_whale_activity(symbol)
            order_book = self.bybit_service.get_order_book(symbol, limit=50)

            # Получаем RSI из исторических данных для более точного определения перекупленности
            rsi = candle_stats.get("rsi")
            rsi_signal = candle_stats.get("rsi_signal", "NEUTRAL")
            
            overbought_status = self._detect_overbought_status(
                change_percent=float(ticker["change_24h"]) * 100,
                funding_rate=float(funding.get("funding_rate", 0)) if funding else 0,
                rsi=rsi,
                rsi_signal=rsi_signal,
                ema_signal=candle_stats.get("ema_signal", "NEUTRAL")
            )

            result_data = {
                "symbol": symbol,
                "current_price": float(ticker["last_price"]),
                "change_24h": float(ticker["change_24h"]) * 100,
                "volume_24h": float(ticker.get("volume_24h", ticker.get("turnover_24h", 0)) or 0),
                "high_24h": float(ticker.get("high_price_24h", 0)),
                "low_24h": float(ticker.get("low_price_24h", 0)),
                "funding_rate": float(funding.get("funding_rate", 0)) if funding else 0,
                "open_interest": oi.get("open_interest", "N/A") if oi else "N/A",
                "volatility": self._calculate_volatility(ticker),
                "liquidity_score": self._calculate_liquidity_score(ticker, oi),
                "overbought_status": overbought_status,
                "price_structure": candle_stats["structure_comment"],
                "historical_trend": candle_stats["trend_description"],
                "analysis_window": candle_stats["window_label"],
                "support_levels": candle_stats["support_levels"],
                "resistance_levels": candle_stats["resistance_levels"],
                "avg_hourly_volume": candle_stats["avg_volume"],
                "range_width": candle_stats["range_width"],
                "day_change": candle_stats["day_change"],
                "week_change": candle_stats["week_change"],
                "ema_50": candle_stats["ema_50"],
                "ema_200": candle_stats["ema_200"],
                "ema_signal": candle_stats["ema_signal"],
                "vwap": candle_stats["vwap"],
                "vwap_distance": candle_stats["vwap_distance"],
                "smart_money": whale_activity,
                "smart_money_bias": whale_activity.get("bias", "NEUTRAL"),
                "smart_money_flow": whale_activity.get("net_flow", 0.0),
                "candle_patterns": candle_stats.get("candle_patterns", {}),
                "order_book_depth": order_book.get("depth_analysis", {}) if order_book else {},
                "rsi": candle_stats.get("rsi"),
                "atr": candle_stats.get("atr"),
                "macd": candle_stats.get("macd"),
                "bollinger_bands": candle_stats.get("bollinger_bands")
            }
            
            # Сохраняем снимок в БД для анализа времени суток
            if self.db_service:
                try:
                    market_snapshot = {
                        "current_price": float(ticker["last_price"]),
                        "volume_24h": float(ticker.get("volume_24h", ticker.get("turnover_24h", 0)) or 0),
                        "volatility": self._calculate_volatility(ticker),
                        "funding_rate": float(funding.get("funding_rate", 0)) if funding else 0,
                        "open_interest": oi.get("open_interest", 0) if oi and oi.get("open_interest") != "N/A" else 0,
                        "liquidity_score": self._calculate_liquidity_score(ticker, oi)
                    }
                    self.db_service.save_market_snapshot(symbol, market_snapshot, candle_stats)
                except Exception as db_error:
                    logger.warning(f"Не удалось сохранить снимок рынка в БД для {symbol}: {db_error}")
            
            return result_data
            
            return result_data
        except Exception as e:
            logger.error(f"Ошибка при получении исторических данных для {symbol}: {e}")
            return None
    
    def _calculate_volatility(self, ticker: Dict) -> float:
        """Рассчитать волатильность на основе high/low 24h"""
        try:
            high = float(ticker.get("high_price_24h", 0))
            low = float(ticker.get("low_price_24h", 0))
            current = float(ticker["last_price"])
            
            if current > 0:
                volatility = ((high - low) / current) * 100
                return round(volatility, 2)
            return 0.0
        except:
            return 0.0
    
    def _calculate_liquidity_score(self, ticker: Dict, oi: Optional[Dict]) -> float:
        """Рассчитать оценку ликвидности (0-10)"""
        try:
            volume = float(ticker.get("volume_24h", 0))
            oi_value = float(oi.get("open_interest", 0)) if oi and oi.get("open_interest") != "N/A" else 0
            
            # Нормализуем объем (чем больше, тем лучше)
            volume_score = min(volume / 1000000000, 1.0) * 5  # Максимум 5 за объем
            
            # Нормализуем OI
            oi_score = min(oi_value / 100000000, 1.0) * 5  # Максимум 5 за OI
            
            return round(volume_score + oi_score, 2)
        except:
            return 0.0

    def _analyze_candles(self, candles: List[Dict]) -> Dict:
        """Анализ исторических свечей (1H) для понимания тренда."""
        if not candles:
            return {
                "trend_description": "недостаточно данных",
                "support_levels": [],
                "resistance_levels": [],
                "avg_volume": 0.0,
                "structure_comment": "Нет данных по свечам",
                "window_label": "история недоступна",
                "range_width": 0.0,
                "day_change": 0.0,
                "week_change": 0.0
            }

        closes = [c["close"] for c in candles]
        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # Анализ теней свечей и паттернов
        candle_patterns = self._analyze_candle_patterns(candles[-20:])  # Последние 20 свечей
        
        recent_close = closes[-1]
        ma_24 = mean(closes[-24:]) if len(closes) >= 24 else mean(closes)
        ma_96 = mean(closes[-96:]) if len(closes) >= 96 else ma_24
        ma_diff_pct = ((ma_24 - ma_96) / ma_96) * 100 if ma_96 else 0

        if ma_diff_pct > 1.5:
            trend = "сильный бычий тренд"
        elif ma_diff_pct > 0.3:
            trend = "умеренный бычий тренд"
        elif ma_diff_pct < -1.5:
            trend = "сильный медвежий тренд"
        elif ma_diff_pct < -0.3:
            trend = "умеренный медвежий тренд"
        else:
            trend = "нейтральное боковое движение"

        day_change = ((recent_close - closes[-24]) / closes[-24]) * 100 if len(closes) >= 24 else 0
        week_change = ((recent_close - closes[0]) / closes[0]) * 100 if closes[0] else 0

        range_high = max(highs[-120:]) if len(highs) >= 120 else max(highs)
        range_low = min(lows[-120:]) if len(lows) >= 120 else min(lows)
        range_width = ((range_high - range_low) / range_low) * 100 if range_low else 0

        recent_slice = candles[-60:]
        support_levels = sorted({round(c["low"], 2) for c in recent_slice})[:3]
        resistance_levels = sorted({round(c["high"], 2) for c in recent_slice}, reverse=True)[:3]

        structure_comment = (
            f"Цена держится {'выше' if recent_close >= ma_24 else 'ниже'} краткосрочного MA (24ч) "
            f"и {'выше' if recent_close >= ma_96 else 'ниже'} среднего MA за 4 дня. "
            f"Диапазон {range_low:.2f}-{range_high:.2f} ({range_width:.1f}% ширина)."
        )

        ema_50 = self._calculate_ema(closes, 50)
        ema_200 = self._calculate_ema(closes, 200)
        ema_signal = "BULLISH" if ema_50 and ema_200 and ema_50 > ema_200 * 1.002 else \
                     "BEARISH" if ema_50 and ema_200 and ema_50 < ema_200 * 0.998 else "NEUTRAL"
        vwap = self._calculate_vwap(candles)
        vwap_distance = ((recent_close - vwap) / vwap) * 100 if vwap else 0
        
        # Calculate RSI and ATR
        rsi = self._calculate_rsi(closes, period=14)
        atr = self._calculate_atr(candles, period=14)
        
        # Determine RSI signal
        rsi_signal = "NEUTRAL"
        if rsi:
            if rsi > 70:
                rsi_signal = "OVERBOUGHT"
            elif rsi < 30:
                rsi_signal = "OVERSOLD"
        
        # Calculate MACD
        macd = self._calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9)
        
        # Calculate Bollinger Bands
        bollinger = self._calculate_bollinger_bands(closes, period=20, std_dev=2.0)

        return {
            "trend_description": trend,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "avg_volume": round(mean(volumes[-48:]), 2) if volumes else 0,
            "structure_comment": structure_comment,
            "window_label": f"{len(candles)}h (≈ {len(candles)//24}d)",
            "range_width": round(range_width, 2),
            "day_change": round(day_change, 2),
            "week_change": round(week_change, 2),
            "ema_50": ema_50,
            "ema_200": ema_200,
            "ema_signal": ema_signal,
            "vwap": vwap,
            "vwap_distance": round(vwap_distance, 2),
            "rsi": rsi,
            "rsi_signal": rsi_signal,
            "atr": atr,
            "macd": macd,
            "bollinger_bands": bollinger,
            "candle_patterns": candle_patterns
        }
    
    def calculate_adaptive_leverage(self, volatility: float, daily_target: float, 
                                   capital: float) -> Dict:
        """
        Рассчитать адаптивное безопасное плечо на основе волатильности
        
        Args:
            volatility: Волатильность в процентах
            daily_target: Целевая прибыль в день
            capital: Капитал
        
        Returns:
            Словарь с рекомендуемым leverage и параметрами
        """
        try:
            # Чем выше волатильность, тем ниже leverage (безопасность)
            if volatility > 10:  # Очень высокая волатильность
                max_leverage = 2
            elif volatility > 5:  # Высокая волатильность
                max_leverage = 3
            elif volatility > 3:  # Средняя волатильность
                max_leverage = 5
            else:  # Низкая волатильность
                max_leverage = 7
            
            # Ограничиваем максимум 10x для безопасности
            max_leverage = min(max_leverage, 10)
            
            # Рассчитываем минимальный leverage для достижения цели
            # daily_target = position_size * price * volatility * leverage * risk_reward
            # Упрощенный расчет
            min_leverage_for_target = max(1, int(daily_target / (capital * 0.01)))
            
            # Выбираем безопасное значение
            recommended_leverage = min(max_leverage, max(1, min_leverage_for_target))
            
            return {
                "recommended_leverage": recommended_leverage,
                "max_safe_leverage": max_leverage,
                "volatility_category": self._get_volatility_category(volatility),
                "risk_level": self._get_risk_level(volatility, recommended_leverage)
            }
        except Exception as e:
            logger.error(f"Ошибка при расчете адаптивного leverage: {e}")
            return {"recommended_leverage": 2, "max_safe_leverage": 2, "risk_level": "LOW"}
    
    def _get_volatility_category(self, volatility: float) -> str:
        """Определить категорию волатильности"""
        if volatility > 10:
            return "ОЧЕНЬ ВЫСОКАЯ"
        elif volatility > 5:
            return "ВЫСОКАЯ"
        elif volatility > 3:
            return "СРЕДНЯЯ"
        else:
            return "НИЗКАЯ"
    
    def _get_risk_level(self, volatility: float, leverage: int) -> str:
        """Определить уровень риска"""
        risk_score = volatility * leverage / 10
        
        if risk_score < 2:
            return "МИНИМАЛЬНЫЙ"
        elif risk_score < 5:
            return "НИЗКИЙ"
        elif risk_score < 10:
            return "СРЕДНИЙ"
        else:
            return "ВЫСОКИЙ"
    
    def calculate_safe_position_size(self, symbol: str, entry_price: float, 
                                    stop_loss: float, leverage: int,
                                    risk_multiplier: float = 1.0) -> Dict:
        """
        Рассчитать безопасный размер позиции для достижения дневной цели
        
        Args:
            symbol: Символ
            entry_price: Цена входа
            stop_loss: Стоп-лосс
            leverage: Leverage
        
        Returns:
            Словарь с параметрами позиции
        """
        try:
            # Рассчитываем риск на сделку с учетом динамического множителя
            risk_amount = self.capital * self.max_daily_risk * risk_multiplier
            risk_amount = max(risk_amount, self.capital * 0.005)
            
            # Рассчитываем размер позиции
            position_size = self.risk_service.calculate_position_size(
                entry_price, stop_loss, risk_amount, leverage
            )
            
            # Рассчитываем тейк-профит на основе risk-reward
            side = "Long" if entry_price > stop_loss else "Short"
            take_profit = self.risk_service.get_recommended_take_profit(
                entry_price, stop_loss, side
            )
            
            # Рассчитываем потенциальную прибыль
            if side == "Long":
                profit_per_unit = take_profit - entry_price
            else:
                profit_per_unit = entry_price - take_profit
            
            potential_profit = position_size * profit_per_unit * leverage
            
            # Рассчитываем notional (объем позиции)
            notional = position_size * entry_price * leverage
            
            return {
                "position_size": round(position_size, 8),
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": round(take_profit, 2),
                "leverage": leverage,
                "risk_amount": round(risk_amount, 2),
                "potential_profit": round(potential_profit, 2),
                "notional": round(notional, 2),
                "risk_multiplier": round(risk_multiplier, 2),
                "risk_reward_ratio": round((take_profit - entry_price) / (entry_price - stop_loss) if side == "Long" else (entry_price - take_profit) / (stop_loss - entry_price), 2)
            }
        except Exception as e:
            logger.error(f"Ошибка при расчете размера позиции: {e}")
            return {}
    
    def analyze_all_coins(self) -> List[Dict]:
        """
        Проанализировать все популярные монеты
        
        Returns:
            Список словарей с анализом каждой монеты
        """
        results = []
        
        for symbol in self.popular_coins:
            try:
                data = self.get_historical_data(symbol)
                if not data:
                    continue
                
                # Рассчитываем адаптивное leverage
                leverage_info = self.calculate_adaptive_leverage(
                    data["volatility"],
                    self.daily_target,
                    self.capital
                )
                
                # Рассчитываем рекомендуемые уровни
                current_price = data["current_price"]
                recommended_stop = self.risk_service.get_recommended_stop_loss(
                    current_price, "Long", data["volatility"] / 100
                )
                
                # Рассчитываем безопасный размер позиции
                risk_multiplier = self._adjust_risk_multiplier(data)
                position_info = self.calculate_safe_position_size(
                    symbol,
                    current_price,
                    recommended_stop,
                    leverage_info["recommended_leverage"],
                    risk_multiplier=risk_multiplier
                )
                
                # Формируем рекомендацию
                recommendation = self._generate_recommendation(data, leverage_info, position_info)
                
                results.append({
                    "symbol": symbol,
                    "data": data,
                    "leverage_info": leverage_info,
                    "position_info": position_info,
                    "recommendation": recommendation,
                    "score": self._calculate_opportunity_score(data, leverage_info, position_info)
                })
                
            except Exception as e:
                logger.error(f"Ошибка при анализе {symbol}: {e}")
                continue
        
        # Сортируем по score (лучшие возможности первыми)
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results
    
    def _generate_recommendation(self, data: Dict, leverage_info: Dict, 
                                position_info: Dict) -> str:
        """Сгенерировать текстовую рекомендацию"""
        try:
            symbol = data["symbol"]
            volatility = data["volatility"]
            funding = data["funding_rate"]
            leverage = leverage_info["recommended_leverage"]
            risk_level = leverage_info["risk_level"]
            potential_profit = position_info.get("potential_profit", 0)
            ema_signal = data.get("ema_signal", "NEUTRAL")
            smart_bias = data.get("smart_money_bias", "NEUTRAL")
            vwap_distance = data.get("vwap_distance", 0)
            
            overbought_status = data.get("overbought_status", "NEUTRAL")

            recommendation = f"""
📊 {symbol}

Волатильность: {volatility}% ({leverage_info['volatility_category']})
Фандинг: {funding*100:.4f}%
Рекомендуемое плечо: {leverage}x
Уровень риска: {risk_level}
Состояние: {overbought_status}
EMA (50/200): {ema_signal}
Крупные игроки: {smart_bias} (нетто {data.get('smart_money_flow', 0):,.0f}$)
Отклонение от VWAP: {vwap_distance:.2f}%

Потенциальная прибыль: ${potential_profit:.2f}
"""
            
            # Добавляем оценку
            if volatility < 3 and funding < 0.01 and risk_level in ["МИНИМАЛЬНЫЙ", "НИЗКИЙ"]:
                recommendation += "✅ ОТЛИЧНАЯ возможность для безопасной торговли"
            elif volatility < 5 and risk_level in ["МИНИМАЛЬНЫЙ", "НИЗКИЙ"]:
                recommendation += "✅ ХОРОШАЯ возможность"
            elif risk_level == "СРЕДНИЙ":
                recommendation += "⚠️ УМЕРЕННЫЙ риск"
            else:
                recommendation += "❌ ВЫСОКИЙ риск - не рекомендуется"
            
            return recommendation
        except Exception as e:
            logger.error(f"Ошибка при генерации рекомендации: {e}")
            return "Не удалось сгенерировать рекомендацию"
    
    def _calculate_opportunity_score(self, data: Dict, leverage_info: Dict, 
                                    position_info: Dict) -> float:
        """
        Рассчитать общий score возможности (0-100)
        Чем выше score, тем лучше возможность
        """
        try:
            score = 50.0  # Базовый score
            
            # Волатильность (ниже = лучше для безопасности)
            volatility = data["volatility"]
            if volatility < 2:
                score += 20
            elif volatility < 3:
                score += 15
            elif volatility < 5:
                score += 10
            elif volatility < 7:
                score += 5
            
            # Funding rate (ближе к 0 = лучше)
            funding = abs(data["funding_rate"])
            if funding < 0.001:
                score += 15
            elif funding < 0.005:
                score += 10
            elif funding < 0.01:
                score += 5
            
            # Ликвидность
            liquidity = data.get("liquidity_score", 0)
            score += liquidity * 2  # Максимум 20 баллов
            
            # Уровень риска
            risk_level = leverage_info["risk_level"]
            if risk_level == "МИНИМАЛЬНЫЙ":
                score += 15
            elif risk_level == "НИЗКИЙ":
                score += 10
            elif risk_level == "СРЕДНИЙ":
                score += 5
            
            # Потенциальная прибыль (ближе к цели = лучше)
            potential_profit = position_info.get("potential_profit", 0)
            if 5 <= potential_profit <= 10:
                score += 10
            elif 3 <= potential_profit < 5 or 10 < potential_profit <= 15:
                score += 5

            # Перекупленность/перепроданность
            status = data.get("overbought_status")
            if status == "OVERBOUGHT":
                score -= 15
            elif status == "OVERSOLD":
                score += 10

            ema_signal = data.get("ema_signal")
            if ema_signal == "BULLISH":
                score += 8
            elif ema_signal == "BEARISH":
                score -= 8

            smart_flow = data.get("smart_money_flow", 0)
            if smart_flow > 100000:
                score += 7
            elif smart_flow < -100000:
                score -= 10
            
            return min(score, 100.0)
        except:
            return 0.0

    def _detect_overbought_status(self, change_percent: float, funding_rate: float, 
                                  rsi: float = None, rsi_signal: str = "NEUTRAL", 
                                  ema_signal: str = "NEUTRAL") -> str:
        """
        Определить состояние рынка (перекупленность/перепроданность)
        Учитывает RSI, EMA сигналы, изменение цены и funding rate
        """
        try:
            # Приоритет 1: RSI - самый надежный индикатор перекупленности/перепроданности
            if rsi_signal == "OVERBOUGHT" or (rsi and rsi > 70):
                # Если RSI показывает перекупленность, но EMA бычий - может быть сильный тренд
                # В таком случае не блокируем Long полностью, но предпочитаем Short
                if ema_signal == "BEARISH":
                    return "OVERBOUGHT"  # Явная перекупленность + медвежий тренд
                elif ema_signal == "BULLISH":
                    return "BALANCED"  # RSI высокий, но тренд бычий - может продолжиться рост
                else:
                    return "OVERBOUGHT"  # RSI высокий без четкого тренда
            
            if rsi_signal == "OVERSOLD" or (rsi and rsi < 30):
                # Если RSI показывает перепроданность, но EMA медвежий - может быть сильный падающий тренд
                if ema_signal == "BULLISH":
                    return "OVERSOLD"  # Явная перепроданность + бычий тренд
                elif ema_signal == "BEARISH":
                    return "BALANCED"  # RSI низкий, но тренд медвежий - может продолжиться падение
                else:
                    return "OVERSOLD"  # RSI низкий без четкого тренда
            
            # Приоритет 2: Комбинация изменения цены и funding rate
            if change_percent > 6 and funding_rate > 0.01:
                return "OVERBOUGHT"
            if change_percent < -6 and funding_rate < -0.005:
                return "OVERSOLD"
            
            # Приоритет 3: EMA сигнал
            if ema_signal == "BEARISH" and change_percent > 3:
                return "OVERBOUGHT"  # Медвежий тренд + рост цены = перекупленность
            if ema_signal == "BULLISH" and change_percent < -3:
                return "OVERSOLD"  # Бычий тренд + падение цены = перепроданность
            
            # Нейтральные случаи
            if abs(change_percent) < 1:
                return "NEUTRAL"
            
            return "BALANCED"
        except Exception:
            return "NEUTRAL"

    def get_market_overview(self, analysis_results: Optional[List[Dict]] = None,
                             market_sentiment: Optional[Dict] = None) -> Dict:
        """
        Сформировать сводную картину рынка, объединяя технический анализ и новостной фон
        """
        if analysis_results is None:
            analysis_results = self.analyze_all_coins()

        if not analysis_results:
            return {}

        avg_volatility = sum(item["data"]["volatility"] for item in analysis_results) / len(analysis_results)
        avg_funding = sum(item["data"]["funding_rate"] for item in analysis_results) / len(analysis_results)
        overbought_count = sum(1 for item in analysis_results if item["data"].get("overbought_status") == "OVERBOUGHT")
        oversold_count = sum(1 for item in analysis_results if item["data"].get("overbought_status") == "OVERSOLD")

        overview = {
            "avg_volatility": round(avg_volatility, 2),
            "avg_funding": round(avg_funding * 100, 4),
            "overbought_count": overbought_count,
            "oversold_count": oversold_count,
            "total_assets": len(analysis_results),
            "best_assets": analysis_results,
            "top_assets": analysis_results[:3],
            "order_flow": self._calculate_order_flow(analysis_results),
            "market_sentiment": market_sentiment,
            "total_volume": sum(asset["data"].get("volume_24h", 0) for asset in analysis_results)
        }

        return overview

    def _calculate_order_flow(self, analysis_results: List[Dict]) -> Dict:
        """
        Вычислить оценку спроса/предложения (покупки/продажи) по количеству возможностей.
        """
        longs = sum(1 for asset in analysis_results if asset["position_info"].get("potential_profit", 0) >= 5)
        shorts = len(analysis_results) - longs

        return {
            "long_orders": longs,
            "short_orders": shorts,
            "trend": "перекуплен (бычий)" if longs > shorts * 1.5 else
                     "перепродан (медвежий)" if shorts > longs * 1.5 else
                     "сбалансирован"
        }

    def _format_volume_value(self, volume: float) -> str:
        """Красивое форматирование объёма сделок."""
        try:
            value = float(volume or 0)
            if value >= 1_000_000_000:
                return f"{value / 1_000_000_000:.2f} млрд USDT"
            if value >= 1_000_000:
                return f"{value / 1_000_000:.2f} млн USDT"
            if value >= 1_000:
                return f"{value / 1_000:.2f} тыс. USDT"
            return f"{value:.2f} USDT"
        except Exception:
            return "N/A"

    def _calculate_ema(self, values: List[float], length: int) -> Optional[float]:
        if not values:
            return None
        if len(values) < length:
            length = len(values)
        k = 2 / (length + 1)
        ema = values[0]
        for price in values[1:]:
            ema = price * k + ema * (1 - k)
        return round(ema, 4)
    
    def _analyze_candle_patterns(self, candles: List[Dict]) -> Dict:
        """Анализ паттернов свечей и теней (фитилей)."""
        if not candles or len(candles) < 2:
            return {
                "recent_patterns": [],
                "wick_analysis": {},
                "rejection_levels": []
            }
        
        recent_patterns = []
        wick_analysis = {
            "upper_wicks_avg": 0.0,
            "lower_wicks_avg": 0.0,
            "body_to_wick_ratio": 0.0
        }
        rejection_levels = []
        
        # Анализ последних 5 свечей
        for i, candle in enumerate(candles[-5:]):
            open_price = candle["open"]
            close_price = candle["close"]
            high_price = candle["high"]
            low_price = candle["low"]
            
            body = abs(close_price - open_price)
            upper_wick = high_price - max(open_price, close_price)
            lower_wick = min(open_price, close_price) - low_price
            total_range = high_price - low_price
            
            # Определение паттерна
            pattern = "NORMAL"
            if body < total_range * 0.1:
                pattern = "DOJI"  # Маленькое тело
            elif upper_wick > body * 2 and lower_wick < body * 0.5:
                pattern = "SHOOTING_STAR" if close_price < open_price else "INVERTED_HAMMER"
            elif lower_wick > body * 2 and upper_wick < body * 0.5:
                pattern = "HAMMER" if close_price > open_price else "HANGING_MAN"
            elif body > total_range * 0.7:
                pattern = "MARUBOZU"  # Большое тело без теней
            
            # Анализ откатов (rejections)
            if upper_wick > body * 1.5:
                rejection_levels.append({
                    "price": high_price,
                    "type": "RESISTANCE",
                    "strength": "STRONG" if upper_wick > body * 2 else "MODERATE"
                })
            if lower_wick > body * 1.5:
                rejection_levels.append({
                    "price": low_price,
                    "type": "SUPPORT",
                    "strength": "STRONG" if lower_wick > body * 2 else "MODERATE"
                })
            
            recent_patterns.append({
                "pattern": pattern,
                "upper_wick_pct": (upper_wick / total_range * 100) if total_range > 0 else 0,
                "lower_wick_pct": (lower_wick / total_range * 100) if total_range > 0 else 0,
                "body_pct": (body / total_range * 100) if total_range > 0 else 0
            })
        
        # Средние значения теней
        if recent_patterns:
            wick_analysis["upper_wicks_avg"] = round(mean([p["upper_wick_pct"] for p in recent_patterns]), 2)
            wick_analysis["lower_wicks_avg"] = round(mean([p["lower_wick_pct"] for p in recent_patterns]), 2)
            wick_analysis["body_to_wick_ratio"] = round(
                mean([p["body_pct"] for p in recent_patterns]) / 
                (mean([p["upper_wick_pct"] + p["lower_wick_pct"] for p in recent_patterns]) + 0.01),
                2
            )
        
        return {
            "recent_patterns": recent_patterns[-3:],  # Последние 3 паттерна
            "wick_analysis": wick_analysis,
            "rejection_levels": rejection_levels[-5:]  # Последние 5 уровней отката
        }

    def _calculate_vwap(self, candles: List[Dict]) -> Optional[float]:
        if not candles:
            return None
        cumulative_vol = 0.0
        cumulative_vp = 0.0
        for candle in candles[-96:]:
            typical = (candle["high"] + candle["low"] + candle["close"]) / 3
            volume = candle["volume"]
            cumulative_vp += typical * volume
            cumulative_vol += volume
        if cumulative_vol == 0:
            return None
        return round(cumulative_vp / cumulative_vol, 4)
    
    def _calculate_rsi(self, closes: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            closes: List of closing prices
            period: RSI period (default 14)
        
        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(closes) < period + 1:
            return None
        
        try:
            gains = []
            losses = []
            
            for i in range(1, len(closes)):
                change = closes[i] - closes[i - 1]
                if change > 0:
                    gains.append(change)
                    losses.append(0.0)
                else:
                    gains.append(0.0)
                    losses.append(abs(change))
            
            if len(gains) < period:
                return None
            
            # Calculate average gain and loss over period
            avg_gain = mean(gains[-period:])
            avg_loss = mean(losses[-period:])
            
            if avg_loss == 0:
                return 100.0  # All gains, no losses
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return round(rsi, 2)
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return None
    
    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> Optional[float]:
        """
        Calculate ATR (Average True Range)
        
        Args:
            candles: List of candle dictionaries with high, low, close
            period: ATR period (default 14)
        
        Returns:
            ATR value or None if insufficient data
        """
        if len(candles) < period + 1:
            return None
        
        try:
            true_ranges = []
            
            for i in range(1, len(candles)):
                high = candles[i]["high"]
                low = candles[i]["low"]
                prev_close = candles[i - 1]["close"]
                
                tr1 = high - low
                tr2 = abs(high - prev_close)
                tr3 = abs(low - prev_close)
                
                true_range = max(tr1, tr2, tr3)
                true_ranges.append(true_range)
            
            if len(true_ranges) < period:
                return None
            
            atr = mean(true_ranges[-period:])
            return round(atr, 4)
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None
    
    def _calculate_macd(self, closes: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Optional[Dict]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            closes: List of closing prices
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line EMA period (default 9)
        
        Returns:
            Dict with MACD, signal, and histogram values or None if insufficient data
        """
        if len(closes) < slow_period + signal_period:
            return None
        
        try:
            # Calculate fast and slow EMAs
            fast_ema = self._calculate_ema(closes, fast_period)
            slow_ema = self._calculate_ema(closes, slow_period)
            
            if not fast_ema or not slow_ema:
                return None
            
            # MACD line = fast EMA - slow EMA
            macd_line = fast_ema - slow_ema
            
            # Calculate MACD values for signal line
            macd_values = []
            for i in range(slow_period, len(closes)):
                fast = self._calculate_ema(closes[:i+1], fast_period)
                slow = self._calculate_ema(closes[:i+1], slow_period)
                if fast and slow:
                    macd_values.append(fast - slow)
            
            if len(macd_values) < signal_period:
                return None
            
            # Signal line = EMA of MACD line
            signal_line = self._calculate_ema(macd_values, signal_period)
            
            if not signal_line:
                return None
            
            # Histogram = MACD line - Signal line
            histogram = macd_line - signal_line
            
            # Determine MACD signal
            if macd_line > signal_line and histogram > 0:
                macd_signal = "BULLISH"
            elif macd_line < signal_line and histogram < 0:
                macd_signal = "BEARISH"
            else:
                macd_signal = "NEUTRAL"
            
            return {
                "macd": round(macd_line, 4),
                "signal": round(signal_line, 4),
                "histogram": round(histogram, 4),
                "macd_signal": macd_signal
            }
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return None
    
    def _calculate_bollinger_bands(self, closes: List[float], period: int = 20, std_dev: float = 2.0) -> Optional[Dict]:
        """
        Calculate Bollinger Bands
        
        Args:
            closes: List of closing prices
            period: Moving average period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)
        
        Returns:
            Dict with upper, middle, lower bands and %B or None if insufficient data
        """
        if len(closes) < period:
            return None
        
        try:
            # Middle band = SMA(period)
            middle_band = mean(closes[-period:])
            
            # Calculate standard deviation
            variance = sum((x - middle_band) ** 2 for x in closes[-period:]) / period
            std = variance ** 0.5
            
            # Upper and lower bands
            upper_band = middle_band + (std_dev * std)
            lower_band = middle_band - (std_dev * std)
            
            # %B = (current price - lower band) / (upper band - lower band)
            current_price = closes[-1]
            if upper_band != lower_band:
                percent_b = (current_price - lower_band) / (upper_band - lower_band)
            else:
                percent_b = 0.5
            
            # Determine position relative to bands
            if current_price > upper_band:
                band_position = "ABOVE_UPPER"  # Overbought
            elif current_price < lower_band:
                band_position = "BELOW_LOWER"  # Oversold
            elif percent_b > 0.8:
                band_position = "NEAR_UPPER"  # Near overbought
            elif percent_b < 0.2:
                band_position = "NEAR_LOWER"  # Near oversold
            else:
                band_position = "MIDDLE"  # Between bands
            
            return {
                "upper_band": round(upper_band, 4),
                "middle_band": round(middle_band, 4),
                "lower_band": round(lower_band, 4),
                "percent_b": round(percent_b, 4),
                "band_position": band_position,
                "band_width": round((upper_band - lower_band) / middle_band * 100, 2)  # Band width as % of middle
            }
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {e}")
            return None

    def _get_whale_activity(self, symbol: str) -> Dict:
        try:
            whale_data = self.bybit_service.get_whale_trades(symbol=symbol)
            if not whale_data:
                return {"bias": "NEUTRAL", "net_flow": 0.0, "top_trades": []}
            return whale_data
        except Exception as e:
            logger.warning(f"Не удалось получить данные по китам для {symbol}: {e}")
            return {"bias": "NEUTRAL", "net_flow": 0.0, "top_trades": []}

    def _adjust_risk_multiplier(self, data: Dict) -> float:
        multiplier = 1.0
        volatility = data.get("volatility", 0)
        if volatility > 6:
            multiplier *= 0.7
        elif volatility > 4:
            multiplier *= 0.85

        smart_flow = data.get("smart_money_flow", 0)
        if smart_flow < -100000:
            multiplier *= 0.8
        elif smart_flow > 100000:
            multiplier *= 1.1

        ema_signal = data.get("ema_signal")
        if ema_signal == "BULLISH":
            multiplier *= 1.1
        elif ema_signal == "BEARISH":
            multiplier *= 0.85

        return max(0.4, min(multiplier, 1.2))

