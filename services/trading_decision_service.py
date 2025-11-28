"""
Сервис для принятия торговых решений на основе анализа рынка
Аналог системы nof1.ai
"""
import logging
from services.bybit_service import BybitService
from services.ai_service import AIService
from datetime import datetime

logger = logging.getLogger(__name__)


class TradingDecisionService:
    def __init__(self):
        self.bybit_service = BybitService()
        self.ai_service = AIService()
        self.fee_hurdle = 0.0015  # 0.15% комиссия
    
    def get_current_positions(self):
        """Получить текущие открытые позиции"""
        try:
            positions = self.bybit_service.get_positions()
            formatted_positions = []
            
            for pos in positions:
                size = float(pos.get("size", 0))
                if size != 0:  # Только позиции с размером
                    side = "Long" if size > 0 else "Short"
                    entry_price = float(pos.get("avgPrice", 0))
                    mark_price = float(pos.get("markPrice", 0))
                    unrealized_pnl = float(pos.get("unrealisedPnl", 0))
                    leverage = pos.get("leverage", "1")
                    liq_price = pos.get("liqPrice", "N/A")
                    symbol = pos.get("symbol", "N/A")
                    
                    # Вычисляем notional
                    notional_usd = abs(size) * mark_price
                    
                    formatted_positions.append({
                        "symbol": symbol,
                        "quantity": size,
                        "side": side,
                        "entry_price": entry_price,
                        "current_price": mark_price,
                        "unrealized_pnl": unrealized_pnl,
                        "leverage": leverage,
                        "liquidation_price": liq_price,
                        "notional_usd": notional_usd
                    })
            
            return formatted_positions
        except Exception as e:
            logger.error(f"Ошибка при получении позиций: {e}")
            return []
    
    def get_available_capital(self):
        """Получить доступный капитал"""
        try:
            balance = self.bybit_service.get_balance()
            if balance:
                return float(balance)
            return 0.0
        except Exception as e:
            logger.error(f"Ошибка при получении баланса: {e}")
            return 0.0
    
    def get_current_nav(self):
        """Получить текущий NAV (Net Asset Value)"""
        try:
            balance = self.get_available_capital()
            positions = self.get_current_positions()
            
            total_pnl = sum(pos["unrealized_pnl"] for pos in positions)
            nav = balance + total_pnl
            
            return nav
        except Exception as e:
            logger.error(f"Ошибка при расчете NAV: {e}")
            return 0.0
    
    def get_current_prices(self, symbols):
        """Получить текущие цены для списка символов"""
        prices = {}
        for symbol in symbols:
            ticker = self.bybit_service.get_ticker(symbol)
            if ticker:
                prices[symbol] = float(ticker["last_price"])
        return prices
    
    def analyze_position(self, position, market_data):
        """Анализ конкретной позиции и принятие решения"""
        symbol = position["symbol"]
        
        # Получаем данные о рынке для символа
        ticker = market_data.get("ticker")
        funding = market_data.get("funding")
        oi = market_data.get("open_interest")
        
        # Формируем промпт для AI
        prompt = self._create_position_analysis_prompt(position, ticker, funding, oi)
        
        # Получаем анализ от AI
        analysis = self.ai_service.analyze_trading_decision(prompt)
        
        return analysis
    
    def _create_position_analysis_prompt(self, position, ticker, funding, oi):
        """Создать промпт для анализа позиции"""
        symbol = position["symbol"]
        side = position["side"]
        entry_price = position["entry_price"]
        current_price = position["current_price"]
        unrealized_pnl = position["unrealized_pnl"]
        leverage = position["leverage"]
        liq_price = position["liquidation_price"]
        
        current_time = datetime.now().strftime("%A, %B %d, %Y %I:%M %p ET")
        
        prompt = f"""Ты профессиональный крипто-трейдер-аналитик, специализирующийся на криптовалютных фьючерсах (BTC, ETH, альткоины). Проанализируй текущую позицию и прими решение: HOLD, ADD, или CLOSE.

CURRENT STATE OF CRYPTO FUTURES MARKETS
It is {current_time}

CURRENT POSITION (Криптовалютный фьючерс)

Symbol: {symbol} (криптовалютный фьючерс)
Side: {side}
Entry Price: ${entry_price}
Current Price: ${current_price}
Unrealized P&L: {unrealized_pnl} USDT
Leverage: {leverage}x (для крипто важно учитывать высокую волатильность)
Liquidation Price: ${liq_price} (расстояние до ликвидации: {abs((float(current_price) - float(liq_price)) / float(current_price) * 100):.2f}%)

MARKET DATA (Крипто-рынок)

Price Structure:
- Current Price: ${current_price}
- 24h Change: {float(ticker.get('change_24h', 0)) * 100:.2f}% (крипто может двигаться 5-20% за день)
- High 24h: ${ticker.get('high_price_24h', 'N/A') if ticker else 'N/A'}
- Low 24h: ${ticker.get('low_price_24h', 'N/A') if ticker else 'N/A'}
- Volume 24h: {ticker.get('volume_24h', 'N/A') if ticker else 'N/A'} (объем торгов)

Funding Rate: {funding.get('funding_rate', 'N/A') if funding else 'N/A'} (в крипто funding может быть 0.01-0.1%+)
Open Interest: {oi.get('open_interest', 'N/A') if oi else 'N/A'} (открытый интерес - важно для крипто)

ANALYSIS REQUIRED (Крипто-специфика)

1. Price Structure Analysis (Крипто-рынок):
   - Тренд на 4H таймфрейме (крипто-рынки имеют сильные тренды)
   - Ключевые уровни поддержки/сопротивления (важно для крипто из-за волатильности)
   - Позиция относительно тренда
   - Корреляция с BTC (если это альткоин) или общим крипто-рынком

2. Funding & OI Analysis (Крипто-специфика):
   - Что означает текущий funding rate? (в крипто funding может быть очень высоким)
   - Сигнал от open interest (высокий OI = риск каскадных ликвидаций)
   - Признаки перекупленности/перепроданности
   - Сравнение с историческими значениями funding для этого крипто-актива

3. Position Risk Assessment (Крипто-риски):
   - Расстояние до ликвидации (крипто может быстро двигаться к ликвидации)
   - Риск/прибыль текущей позиции (учитывая высокую волатильность крипто)
   - Корреляция с BTC и общим крипто-рынком
   - Риск каскадных ликвидаций (особенно актуально для крипто)
   - Риск гэпов и низкой ликвидности (для альткоинов)

4. Trading Decision (Крипто-решение):
   Прими решение: HOLD, ADD, или CLOSE для криптовалютного фьючерса

   Если HOLD:
   - Обоснование почему позиция все еще валидна (с учетом крипто-специфики)
   - Уровни stop loss и take profit (реалистичные для крипто-рынка)
   - Условия инвалидации
   - Confidence (0.0-1.0, минимум 0.70 для торговли)
   - Risk USD (максимальный риск, учитывая волатильность крипто)

   Если ADD:
   - Обоснование для увеличения позиции (крипто может быстро двигаться)
   - Размер добавления (консервативный для крипто)
   - Новые уровни stop loss и take profit
   - Confidence (0.0-1.0)
   - Risk USD

   Если CLOSE:
   - Обоснование для закрытия (крипто-рынки могут быстро разворачиваться)
   - Условия, при которых стоит переоткрыть

Формат ответа (JSON):
{{
    "signal": "hold|add|close",
    "justification": "детальное обоснование",
    "confidence": 0.75,
    "risk_usd": 100.0,
    "stop_loss": 405.0,
    "profit_target": 383.0,
    "invalidation_condition": "Price above 405.00",
    "quantity": 12.45,
    "leverage": 10,
    "is_add": false
}}

Важно (Крипто-специфика):
- Если signal="hold", is_add должен быть false
- Если signal="add", is_add должен быть true
- Risk USD должен учитывать расстояние до stop loss и высокую волатильность крипто
- Confidence должен отражать уверенность в решении (минимум 0.70 для торговли крипто)
- Все цены и уровни должны быть конкретными числами
- Учитывай, что крипто-рынки более волатильны (5-20% движения за день - норма)
- Учитывай риск каскадных ликвидаций в крипто
- Leverage для крипто обычно 2-10x, не более (высокая волатильность)
- Учитывай корреляцию с BTC и общим крипто-рынком"""
        
        return prompt
    
    def generate_trading_decisions(self):
        """Генерировать торговые решения для всех позиций"""
        try:
            # Получаем текущее состояние
            positions = self.get_current_positions()
            available_capital = self.get_available_capital()
            nav = self.get_current_nav()
            
            # Получаем цены для всех символов
            symbols = [pos["symbol"] for pos in positions]
            prices = self.get_current_prices(symbols)
            
            decisions = []
            
            for position in positions:
                symbol = position["symbol"]
                
                # Получаем комплексные данные о рынке
                market_data = self.bybit_service.get_market_data_comprehensive(symbol)
                
                if not market_data:
                    logger.warning(f"Не удалось получить данные для {symbol}")
                    continue
                
                # Анализируем позицию
                analysis = self.analyze_position(position, market_data)
                
                # Парсим JSON ответ от AI
                decision = self._parse_ai_decision(analysis, position)
                
                if decision:
                    decisions.append(decision)
            
            return {
                "available_capital": available_capital,
                "nav": nav,
                "current_prices": prices,
                "positions": positions,
                "decisions": decisions
            }
        except Exception as e:
            logger.error(f"Ошибка при генерации торговых решений: {e}", exc_info=True)
            return None

    def _parse_ai_decision(self, ai_response, position):
        """Парсить JSON ответ от AI"""
        import json
        import re
        
        try:
            # Пытаемся найти JSON в ответе
            json_match = re.search(r'\{[^{}]*\}', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                decision = json.loads(json_str)
                
                # Добавляем обязательные поля
                decision["coin"] = position["symbol"]
                decision["symbol"] = position["symbol"]
                
                # Если не указано, используем текущие значения
                if "quantity" not in decision:
                    decision["quantity"] = abs(position["quantity"])
                if "leverage" not in decision:
                    decision["leverage"] = position["leverage"]
                
                return decision
            else:
                # Если JSON не найден, создаем базовое решение HOLD
                logger.warning(f"Не удалось распарсить JSON из ответа AI: {ai_response}")
                return {
                    "signal": "hold",
                    "coin": position["symbol"],
                    "symbol": position["symbol"],
                    "quantity": abs(position["quantity"]),
                    "leverage": position["leverage"],
                    "is_add": False,
                    "justification": "Не удалось получить анализ от AI",
                    "confidence": 0.5,
                    "risk_usd": 0.0
                }
        except Exception as e:
            logger.error(f"Ошибка при парсинге решения AI: {e}")
            return None

