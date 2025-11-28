# Code review marker
"""
Сервис управления рисками для безопасного трейдинга на фьючерсах
Включает: stop loss, take profit, position sizing, leverage control, correlation limits
"""
import logging
from services.bybit_service import BybitService
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)


class RiskManagementService:
    def __init__(self, db_service=None):
        self.bybit_service = BybitService()
        self.db_service = db_service  # Для динамического расчета корреляции
        
        # Параметры управления рисками
        # Значение max_risk_per_trade можно переопределить через переменную окружения AUTO_RISK_PER_TRADE
        self.max_risk_per_trade = getattr(config, "AUTO_RISK_PER_TRADE", 0.02)
        self.max_total_risk = 0.10  # Максимальный общий риск: 10% от капитала
        self.max_leverage = 10  # Максимальный leverage для крипто
        self.min_risk_reward_ratio = 1.5  # Минимальное соотношение риск/прибыль: 1:1.5
        self.max_correlation = 0.9  # Максимальная корреляция между позициями (повышено для BTC/ETH и других основных активов)
        self.max_drawdown = 0.20  # Максимальная просадка: 20%
        
        # Параметры для trailing stop
        self.trailing_stop_enabled = True
        self.trailing_stop_percent = 0.02  # 2% trailing stop
        
        # Параметры для частичного закрытия
        self.partial_close_enabled = True
        self.partial_close_percent = 0.5  # Закрывать 50% при достижении 50% тейк-профита
        
        # Дневной лимит убытков
        self.max_daily_loss_percent = 0.05  # Максимальный дневной убыток: 5% от капитала
        self.daily_loss_tracking = {}  # Отслеживание дневных убытков по датам
        
        # Корреляционная матрица для популярных пар (fallback, если нет данных в БД)
        self.correlation_matrix = {
            "BTCUSDT": {"ETHUSDT": 0.85, "SOLUSDT": 0.75, "BNBUSDT": 0.70},
            "ETHUSDT": {"BTCUSDT": 0.85, "SOLUSDT": 0.80, "BNBUSDT": 0.75},
            "SOLUSDT": {"BTCUSDT": 0.75, "ETHUSDT": 0.80, "BNBUSDT": 0.65},
            "BNBUSDT": {"BTCUSDT": 0.70, "ETHUSDT": 0.75, "SOLUSDT": 0.65},
        }
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, 
                               risk_amount: float, leverage: int = 1) -> float:
        """
        Рассчитать размер позиции на основе риска
        
        Args:
            entry_price: Цена входа
            stop_loss: Цена стоп-лосса
            risk_amount: Сумма риска в USDT
            leverage: Левередж
        
        Returns:
            Размер позиции в контрактах/монетах
        """
        try:
            # Расстояние до стоп-лосса в процентах
            if entry_price > stop_loss:  # Long позиция
                stop_distance = (entry_price - stop_loss) / entry_price
            else:  # Short позиция
                stop_distance = (stop_loss - entry_price) / entry_price
            
            if stop_distance <= 0:
                logger.warning(f"Некорректное расстояние до стоп-лосса: {stop_distance}")
                return 0.0
            
            # Размер позиции с учетом leverage
            # risk_amount = position_size * entry_price * stop_distance * leverage
            # position_size = risk_amount / (entry_price * stop_distance * leverage)
            position_size = risk_amount / (entry_price * stop_distance * leverage)
            
            return round(position_size, 8)
        except Exception as e:
            logger.error(f"Ошибка при расчете размера позиции: {e}")
            return 0.0
    
    def calculate_risk_amount(self, capital: float, risk_percent: float = None) -> float:
        """
        Рассчитать сумму риска на основе процента от капитала
        
        Args:
            capital: Текущий капитал
            risk_percent: Процент риска (по умолчанию max_risk_per_trade)
        
        Returns:
            Сумма риска в USDT
        """
        if risk_percent is None:
            risk_percent = self.max_risk_per_trade
        
        return capital * risk_percent
    
    def validate_stop_loss(self, entry_price: float, stop_loss: float, 
                          side: str, min_stop_distance: float = 0.005) -> bool:
        """
        Валидация стоп-лосса
        
        Args:
            entry_price: Цена входа
            stop_loss: Цена стоп-лосса
            side: "Long" или "Short"
            min_stop_distance: Минимальное расстояние в процентах (0.5%)
        
        Returns:
            True если стоп-лосс валиден
        """
        try:
            if side.lower() == "long":
                if stop_loss >= entry_price:
                    logger.warning(f"Стоп-лосс для лонга должен быть ниже цены входа")
                    return False
                stop_distance = (entry_price - stop_loss) / entry_price
            else:  # Short
                if stop_loss <= entry_price:
                    logger.warning(f"Стоп-лосс для шорта должен быть выше цены входа")
                    return False
                stop_distance = (stop_loss - entry_price) / entry_price
            
            if stop_distance < min_stop_distance:
                logger.warning(f"Стоп-лосс слишком близко к цене входа: {stop_distance*100:.2f}%")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при валидации стоп-лосса: {e}")
            return False
    
    def validate_take_profit(self, entry_price: float, take_profit: float, 
                           stop_loss: float, side: str) -> bool:
        """
        Валидация тейк-профита на основе risk-reward ratio
        
        Args:
            entry_price: Цена входа
            take_profit: Цена тейк-профита
            stop_loss: Цена стоп-лосса
            side: "Long" или "Short"
        
        Returns:
            True если тейк-профит валиден
        """
        try:
            # Рассчитываем риск и прибыль
            if side.lower() == "long":
                risk = entry_price - stop_loss
                reward = take_profit - entry_price
            else:  # Short
                risk = stop_loss - entry_price
                reward = entry_price - take_profit
            
            if risk <= 0 or reward <= 0:
                logger.warning(f"Некорректные значения риска или прибыли")
                return False
            
            risk_reward_ratio = reward / risk
            
            if risk_reward_ratio < self.min_risk_reward_ratio:
                logger.warning(f"Risk-reward ratio слишком низкий: {risk_reward_ratio:.2f}, минимум: {self.min_risk_reward_ratio}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при валидации тейк-профита: {e}")
            return False
    
    def validate_leverage(self, leverage: int) -> bool:
        """
        Валидация leverage
        
        Args:
            leverage: Левередж
        
        Returns:
            True если leverage валиден
        """
        if leverage < 1:
            logger.warning(f"Leverage не может быть меньше 1")
            return False
        
        if leverage > self.max_leverage:
            logger.warning(f"Leverage превышает максимум: {leverage} > {self.max_leverage}")
            return False
        
        return True
    
    def calculate_trailing_stop(self, entry_price: float, current_price: float, 
                               initial_stop_loss: float, side: str) -> float:
        """
        Рассчитать trailing stop
        
        Args:
            entry_price: Цена входа
            current_price: Текущая цена
            initial_stop_loss: Начальный стоп-лосс
            side: "Long" или "Short"
        
        Returns:
            Новая цена trailing stop
        """
        if not self.trailing_stop_enabled:
            return initial_stop_loss
        
        try:
            if side.lower() == "long":
                # Для лонга: trailing stop движется вверх
                profit = current_price - entry_price
                if profit > 0:
                    # Новый стоп-лосс = текущая цена - trailing_stop_percent
                    new_stop = current_price * (1 - self.trailing_stop_percent)
                    # Не опускаем стоп ниже начального
                    return max(new_stop, initial_stop_loss)
            else:  # Short
                # Для шорта: trailing stop движется вниз
                profit = entry_price - current_price
                if profit > 0:
                    # Новый стоп-лосс = текущая цена + trailing_stop_percent
                    new_stop = current_price * (1 + self.trailing_stop_percent)
                    # Не поднимаем стоп выше начального
                    return min(new_stop, initial_stop_loss)
            
            return initial_stop_loss
        except Exception as e:
            logger.error(f"Ошибка при расчете trailing stop: {e}")
            return initial_stop_loss
    
    def check_total_risk(self, positions: List[Dict], capital: float) -> Dict:
        """
        Проверить общий риск всех позиций
        
        Args:
            positions: Список позиций
            capital: Текущий капитал
        
        Returns:
            Словарь с информацией о рисках
        """
        try:
            total_risk = 0.0
            total_notional = 0.0
            total_unrealized_pnl = 0.0
            
            for pos in positions:
                # Рассчитываем риск позиции
                entry_price = float(pos.get("entry_price", 0))
                current_price = float(pos.get("current_price", 0))
                size = abs(float(pos.get("quantity", 0)))
                leverage = int(pos.get("leverage", 1))
                liq_price = float(pos.get("liquidation_price", 0)) if pos.get("liquidation_price") != "N/A" else 0
                
                if entry_price > 0 and size > 0:
                    # Риск = расстояние до ликвидации * размер позиции
                    if liq_price > 0:
                        if entry_price > liq_price:  # Long
                            risk_distance = (current_price - liq_price) / current_price
                        else:  # Short
                            risk_distance = (liq_price - current_price) / current_price
                        
                        position_risk = size * current_price * risk_distance * leverage
                        total_risk += position_risk
                    
                    notional = size * current_price * leverage
                    total_notional += notional
                
                total_unrealized_pnl += float(pos.get("unrealized_pnl", 0))
            
            risk_percent = (total_risk / capital * 100) if capital > 0 else 0
            drawdown = abs(total_unrealized_pnl / capital) if capital > 0 else 0
            
            return {
                "total_risk": total_risk,
                "total_risk_percent": risk_percent,
                "total_notional": total_notional,
                "total_unrealized_pnl": total_unrealized_pnl,
                "drawdown_percent": drawdown * 100,
                "is_risk_acceptable": risk_percent <= (self.max_total_risk * 100),
                "is_drawdown_acceptable": drawdown <= self.max_drawdown
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке общего риска: {e}")
            return {
                "total_risk": 0.0,
                "total_risk_percent": 0.0,
                "is_risk_acceptable": True,
                "is_drawdown_acceptable": True
            }
    
    def get_recommended_stop_loss(self, entry_price: float, side: str, 
                                  volatility_percent: float = 0.02, 
                                  atr: Optional[float] = None) -> float:
        """
        Получить рекомендуемый стоп-лосс на основе волатильности или ATR
        
        Args:
            entry_price: Цена входа
            side: "Long" или "Short"
            volatility_percent: Процент волатильности (по умолчанию 2%)
            atr: ATR значение (если доступно, используется вместо volatility_percent)
        
        Returns:
            Рекомендуемая цена стоп-лосса
        """
        try:
            # Если доступен ATR, используем его (более точный расчет)
            if atr and atr > 0:
                # Используем ATR * 2 для стоп-лосса (стандартная практика)
                atr_multiplier = 2.0
                stop_distance = (atr * atr_multiplier) / entry_price
                
                # Ограничиваем минимальное расстояние 0.5% и максимальное 5%
                stop_distance = max(0.005, min(stop_distance, 0.05))
                
                if side.lower() == "long":
                    return entry_price * (1 - stop_distance)
                else:  # Short
                    return entry_price * (1 + stop_distance)
            
            # Fallback на volatility_percent если ATR недоступен
            if side.lower() == "long":
                return entry_price * (1 - volatility_percent)
            else:  # Short
                return entry_price * (1 + volatility_percent)
        except Exception as e:
            logger.error(f"Ошибка при расчете рекомендуемого стоп-лосса: {e}")
            return entry_price
    
    def get_recommended_take_profit(self, entry_price: float, stop_loss: float, 
                                   side: str) -> float:
        """
        Получить рекомендуемый тейк-профит на основе risk-reward ratio
        
        Args:
            entry_price: Цена входа
            stop_loss: Цена стоп-лосса
            side: "Long" или "Short"
        
        Returns:
            Рекомендуемая цена тейк-профита
        """
        try:
            if side.lower() == "long":
                risk = entry_price - stop_loss
                reward = risk * self.min_risk_reward_ratio
                return entry_price + reward
            else:  # Short
                risk = stop_loss - entry_price
                reward = risk * self.min_risk_reward_ratio
                return entry_price - reward
        except Exception as e:
            logger.error(f"Ошибка при расчете рекомендуемого тейк-профита: {e}")
            return entry_price
    
    def should_partial_close(self, entry_price: float, current_price: float, 
                           take_profit: float, side: str) -> bool:
        """
        Определить, нужно ли частично закрыть позицию
        
        Args:
            entry_price: Цена входа
            current_price: Текущая цена
            take_profit: Цена тейк-профита
            side: "Long" или "Short"
        
        Returns:
            True если нужно частично закрыть
        """
        if not self.partial_close_enabled:
            return False
        
        try:
            if side.lower() == "long":
                profit_to_tp = take_profit - entry_price
                current_profit = current_price - entry_price
            else:  # Short
                profit_to_tp = entry_price - take_profit
                current_profit = entry_price - current_price
            
            if profit_to_tp > 0:
                profit_percent = current_profit / profit_to_tp
                # Закрываем 50% при достижении 50% тейк-профита
                return profit_percent >= self.partial_close_percent
            
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке частичного закрытия: {e}")
            return False
    
    def validate_trade(self, entry_price: float, stop_loss: float, take_profit: float,
                      side: str, leverage: int, capital: float, risk_percent: float = None) -> Dict:
        """
        Полная валидация сделки
        
        Args:
            entry_price: Цена входа
            stop_loss: Цена стоп-лосса
            take_profit: Цена тейк-профита
            side: "Long" или "Short"
            leverage: Левередж
            capital: Капитал
            risk_percent: Процент риска
        
        Returns:
            Словарь с результатами валидации
        """
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "recommendations": {}
        }
        
        # Валидация leverage
        if not self.validate_leverage(leverage):
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Leverage {leverage} превышает максимум {self.max_leverage}")
        
        # Валидация стоп-лосса
        if not self.validate_stop_loss(entry_price, stop_loss, side):
            validation_result["is_valid"] = False
            validation_result["errors"].append("Стоп-лосс невалиден")
        
        # Валидация тейк-профита
        if not self.validate_take_profit(entry_price, take_profit, stop_loss, side):
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Risk-reward ratio меньше минимума {self.min_risk_reward_ratio}")
        
        # Расчет размера позиции
        if risk_percent is None:
            risk_percent = self.max_risk_per_trade
        
        risk_amount = self.calculate_risk_amount(capital, risk_percent)
        position_size = self.calculate_position_size(entry_price, stop_loss, risk_amount, leverage)
        
        validation_result["recommendations"] = {
            "risk_amount": risk_amount,
            "position_size": position_size,
            "recommended_stop_loss": self.get_recommended_stop_loss(entry_price, side),
            "recommended_take_profit": self.get_recommended_take_profit(entry_price, stop_loss, side)
        }
        
        return validation_result
    
    def check_correlation(self, new_symbol: str, existing_positions: List[Dict], new_side: str = None) -> Dict:
        """
        Проверить корреляцию новой позиции с существующими
        Учитывает направление позиций: противоположные направления (хеджирование) разрешены
        
        Args:
            new_symbol: Символ новой позиции
            existing_positions: Список существующих позиций
            new_side: Направление новой позиции ("Long" или "Short"), опционально
        
        Returns:
            Словарь с результатами проверки корреляции
        """
        try:
            if not existing_positions:
                return {"is_safe": True, "max_correlation": 0.0, "warnings": []}
            
            existing_symbols = [pos.get("symbol", "").upper() for pos in existing_positions if pos.get("symbol")]
            new_symbol_upper = new_symbol.upper()
            
            max_correlation = 0.0
            warnings = []
            has_hedge = False  # Есть ли хеджирование (противоположные направления)
            
            for existing_pos in existing_positions:
                existing_symbol = existing_pos.get("symbol", "").upper()
                if not existing_symbol:
                    continue
                    
                correlation = 0.0
                
                # ВРЕМЕННО: Не используем БД для расчета корреляции, пока база наполняется
                # Используем только статическую матрицу корреляций
                correlation = self.correlation_matrix.get(new_symbol_upper, {}).get(existing_symbol, 0.0)
                if correlation == 0:
                    correlation = self.correlation_matrix.get(existing_symbol, {}).get(new_symbol_upper, 0.0)
                
                logger.debug(f"Использование статической корреляции {new_symbol_upper}-{existing_symbol}: {correlation:.2f} (БД временно отключена)")
                
                if correlation > max_correlation:
                    max_correlation = correlation
                
                # Проверяем направление позиций, если указано
                if new_side and correlation > self.max_correlation:
                    existing_side_raw = existing_pos.get("side", "")
                    # Нормализуем side: Bybit возвращает "Buy"/"Sell", БД может хранить "Long"/"Short"
                    existing_side_upper = existing_side_raw.upper()
                    if existing_side_upper in ["BUY", "LONG"]:
                        existing_side_normalized = "LONG"
                    elif existing_side_upper in ["SELL", "SHORT"]:
                        existing_side_normalized = "SHORT"
                    else:
                        existing_side_normalized = existing_side_upper
                    
                    new_side_upper = new_side.upper()
                    if new_side_upper in ["BUY", "LONG"]:
                        new_side_normalized = "LONG"
                    elif new_side_upper in ["SELL", "SHORT"]:
                        new_side_normalized = "SHORT"
                    else:
                        new_side_normalized = new_side_upper
                    
                    # Если направления противоположные - это хеджирование, разрешаем
                    if (new_side_normalized == "LONG" and existing_side_normalized == "SHORT") or \
                       (new_side_normalized == "SHORT" and existing_side_normalized == "LONG"):
                        has_hedge = True
                        logger.info(f"Хеджирование обнаружено: {new_symbol_upper} {new_side} vs {existing_symbol} {existing_side_raw}, корреляция {correlation:.2f}")
                        continue  # Пропускаем предупреждение для хеджирования
                
                if correlation > self.max_correlation:
                    warnings.append(
                        f"Высокая корреляция между {new_symbol_upper} и {existing_symbol}: {correlation:.2f}"
                    )
            
            # Если есть хеджирование, разрешаем даже при высокой корреляции
            if has_hedge:
                is_safe = True
                logger.info(f"Позиция {new_symbol_upper} разрешена из-за хеджирования с существующими позициями")
            else:
                is_safe = max_correlation <= self.max_correlation
            
            return {
                "is_safe": is_safe,
                "max_correlation": max_correlation,
                "warnings": warnings,
                "has_hedge": has_hedge
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке корреляции: {e}")
            return {"is_safe": True, "max_correlation": 0.0, "warnings": []}
    
    def check_daily_loss_limit(self, capital: float, current_pnl: float = 0.0, positions: List[Dict] = None) -> Dict:
        """
        Проверить дневной лимит убытков
        Учитывает unrealized PnL текущих позиций
        
        Args:
            capital: Текущий капитал
            current_pnl: Текущий PnL за день (отрицательный = убыток)
            positions: Список текущих позиций для расчета unrealized PnL
        
        Returns:
            Словарь с результатами проверки лимита
        """
        try:
            today = datetime.utcnow().date().isoformat()
            
            # Получаем текущий дневной убыток
            if today not in self.daily_loss_tracking:
                self.daily_loss_tracking[today] = 0.0
            
            # Рассчитываем unrealized PnL из текущих позиций
            unrealized_loss = 0.0
            if positions:
                for pos in positions:
                    unrealized_pnl = float(pos.get("unrealisedPnl", 0) or 0)
                    if unrealized_pnl < 0:  # Только убытки
                        unrealized_loss += abs(unrealized_pnl)
            
            # Обновляем дневной убыток: учитываем и realized, и unrealized убытки
            daily_loss = abs(min(current_pnl, 0))  # Realized убытки (отрицательные значения)
            total_daily_loss = daily_loss + unrealized_loss  # Общий убыток за день
            
            self.daily_loss_tracking[today] = max(self.daily_loss_tracking[today], total_daily_loss)
            
            # Рассчитываем процент убытка от капитала
            loss_percent = (self.daily_loss_tracking[today] / capital) if capital > 0 else 0.0
            
            # Проверяем лимит
            is_limit_reached = loss_percent >= self.max_daily_loss_percent
            
            # Очищаем старые записи (старше 7 дней)
            cutoff_date = (datetime.utcnow() - timedelta(days=7)).date().isoformat()
            self.daily_loss_tracking = {
                k: v for k, v in self.daily_loss_tracking.items() 
                if k >= cutoff_date
            }
            
            return {
                "is_limit_reached": is_limit_reached,
                "daily_loss": self.daily_loss_tracking[today],
                "daily_loss_percent": loss_percent * 100,
                "max_daily_loss_percent": self.max_daily_loss_percent * 100,
                "remaining_loss_capacity": max(0, (self.max_daily_loss_percent * capital) - self.daily_loss_tracking[today]),
                "unrealized_loss": unrealized_loss,
                "realized_loss": daily_loss
            }
        except Exception as e:
            logger.error(f"Ошибка при проверке дневного лимита убытков: {e}")
            return {
                "is_limit_reached": False,
                "daily_loss": 0.0,
                "daily_loss_percent": 0.0,
                "max_daily_loss_percent": self.max_daily_loss_percent * 100,
                "remaining_loss_capacity": self.max_daily_loss_percent * 100,
                "unrealized_loss": 0.0,
                "realized_loss": 0.0
            }
    
    def reset_daily_loss_tracking(self):
        """Сбросить отслеживание дневных убытков (для тестирования)"""
        self.daily_loss_tracking = {}

