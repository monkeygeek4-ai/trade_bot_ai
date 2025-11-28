# Code review: AI service analysis
import os
import json
from typing import List, Dict, Optional
from openai import OpenAI, APITimeoutError
import config


# Температуры для разных задач
# Более высокая = креативнее, более низкая = стабильнее и детерминированнее
TEMPERATURE_ANALYSIS = 1.0      # Детальные текстовые отчёты / анализ рынка
TEMPERATURE_ADVICE = 0.8        # Краткие советы
TEMPERATURE_TRADE_PLAN = 0.0    # Строгие JSON-планы сделок и выбор монет (максимальная детерминированность)


class AIService:
    def __init__(self):
        """
        Инициализация AI клиента.
        Приоритет:
        1) Если задан DEEPSEEK_API_KEY → работаем напрямую с DeepSeek (deepseek-reasoner).
        2) Иначе используем старый режим через Hugging Face router.
        """
        if getattr(config, "DEEPSEEK_API_KEY", None):
            self.client = OpenAI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=getattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                timeout=60.0,  # Таймаут 60 секунд для AI запросов
            )
            # Рекомендуемая модель от DeepSeek
            self.model = "deepseek-reasoner"
        else:
            self.client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=config.HF_TOKEN,
                timeout=60.0,  # Таймаут 60 секунд для AI запросов
            )
            self.model = config.AI_MODEL
    
    def analyze_market(self, market_data, db_service = None):
        """Детальный анализ фьючерсного рынка с помощью AI (аналогично профессиональному трейдинговому анализу)"""
        
        # Извлекаем данные
        ticker = market_data.get('ticker', {})
        funding = market_data.get('funding', {})
        oi = market_data.get('open_interest', {})
        position = market_data.get('current_position')
        balance = market_data.get('balance', '0')
        historical = market_data.get("historical") or {}
        analysis_window = historical.get("analysis_window", "N/A")
        trend_desc = historical.get("historical_trend") or historical.get("trend_description", "нет данных")
        support_levels = historical.get("support_levels", [])
        resistance_levels = historical.get("resistance_levels", [])
        structure_comment = historical.get("price_structure") or historical.get("structure_comment", "нет описания")
        avg_hourly_volume = historical.get("avg_hourly_volume", 0)
        day_change_hist = historical.get("day_change", 0)
        week_change_hist = historical.get("week_change", 0)
        ema_50 = historical.get("ema_50")
        ema_200 = historical.get("ema_200")
        ema_signal = historical.get("ema_signal", "NEUTRAL")
        vwap = historical.get("vwap")
        vwap_distance = historical.get("vwap_distance", 0)
        smart_money = historical.get("smart_money") or {}
        smart_bias = smart_money.get("bias", "NEUTRAL")
        smart_net_flow = smart_money.get("net_flow", 0)
        candle_patterns = historical.get("candle_patterns", {})
        order_book_depth = historical.get("order_book_depth", {})
        
        symbol = ticker.get('symbol', 'N/A')
        last_price = ticker.get('last_price', 'N/A')
        change_24h = float(ticker.get('change_24h', 0)) * 100
        volume_24h = ticker.get('volume_24h', '0')
        bid_price = ticker.get('bid_price', 'N/A')
        ask_price = ticker.get('ask_price', 'N/A')
        high_24h = ticker.get('high_price_24h', 'N/A')
        low_24h = ticker.get('low_price_24h', 'N/A')
        
        funding_rate = funding.get('funding_rate', 'N/A') if funding else 'N/A'
        open_interest = oi.get('open_interest', 'N/A') if oi else 'N/A'
        
        # Form detailed prompt for crypto futures
        prompt = f"""You are a professional crypto trader-analyst specializing in crypto futures markets (BTC, ETH, altcoins). Analyze the following data and provide a detailed analysis in the style of a professional trading report.

CURRENT STATE OF CRYPTO FUTURES MARKET

1. Raw Data Dashboard

{symbol} (Crypto Futures)

Price Structure:
- Current price: ${last_price}
- Bid: ${bid_price} | Ask: ${ask_price}
- High 24h: ${high_24h} | Low 24h: ${low_24h}
- 24h change: {change_24h:.2f}%

Net Funding Rate: {funding_rate} ({'positive (longs pay shorts)' if isinstance(funding_rate, str) == False and float(funding_rate) > 0 else 'negative (shorts pay longs)' if isinstance(funding_rate, str) == False and float(funding_rate) < 0 else 'N/A'})

Open Interest (OI): {open_interest} (total volume of open positions)

Volume 24h: {volume_24h} (trading volume over 24 hours)

Current position: {f"Size: {position.get('size')}, Side: {position.get('side')}, P&L: {position.get('unrealised_pnl')}, Leverage: {position.get('leverage')}x" if position else "No open position"}

Available balance: {balance} USDT

Historical Context (1H candle data):
- Analysis window: {analysis_window}
- Candle structure: {structure_comment}
- Current trend: {trend_desc}
- 24h/7d change: {day_change_hist:.2f}% / {week_change_hist:.2f}%
- Average hourly volume: {avg_hourly_volume}
- Key supports: {support_levels if support_levels else 'no data'}
- Key resistances: {resistance_levels if resistance_levels else 'no data'}
- EMA(50/200): {ema_50} / {ema_200} (signal: {ema_signal})
- VWAP: {vwap} (deviation {vwap_distance:.2f}%)
- Smart money: {smart_bias}, net_flow: {smart_net_flow:,.0f} USDT

Order Book Depth Analysis:
- Order book imbalance: {order_book_depth.get('imbalance_ratio', 0):.4f} ({'support > resistance' if order_book_depth.get('imbalance_ratio', 0) > 0 else 'resistance > support' if order_book_depth.get('imbalance_ratio', 0) < 0 else 'balanced'})
- Liquidity quality: {order_book_depth.get('depth_quality', 'N/A')}
- Support volume: {order_book_depth.get('support_volume', 0):,.0f} | Resistance volume: {order_book_depth.get('resistance_volume', 0):,.0f}
- Key support levels in order book: {', '.join([f"${l['price']:.2f} ({l['size']:.2f})" for l in order_book_depth.get('support_levels', [])[:3]]) if order_book_depth.get('support_levels') else 'no data'}
- Key resistance levels in order book: {', '.join([f"${l['price']:.2f} ({l['size']:.2f})" for l in order_book_depth.get('resistance_levels', [])[:3]]) if order_book_depth.get('resistance_levels') else 'no data'}

Candlestick Patterns Analysis:
- Recent patterns: {', '.join([p.get('pattern', 'NORMAL') for p in candle_patterns.get('recent_patterns', [])]) if candle_patterns.get('recent_patterns') else 'no data'}
- Average wicks: upper {candle_patterns.get('wick_analysis', {}).get('upper_wicks_avg', 0):.2f}% | lower {candle_patterns.get('wick_analysis', {}).get('lower_wicks_avg', 0):.2f}%
- Body to wick ratio: {candle_patterns.get('wick_analysis', {}).get('body_to_wick_ratio', 0):.2f}
- Rejection levels: {len(candle_patterns.get('rejection_levels', []))} levels detected

2. Price Structure Analysis

Analyze price structure for crypto futures:
- Trend on 4H timeframe (bullish/bearish/sideways)
- Key support and resistance levels (important for crypto due to high volatility)
- Volatility and volumes (crypto markets are more volatile than traditional)
- Correlation with BTC (if altcoin) or overall market

3. Funding Rate & Open Interest Analysis

Analyze for crypto futures:
- What does current funding rate mean? (in crypto funding can be very high, up to 0.1%+)
- What signal does open interest give? (high OI = high liquidity, but also risk of cascade liquidations)
- Are there signs of overbought/oversold through funding?
- Compare with historical funding values for this asset

4. The "Pain Trade" (Liquidation Hunting)

Identify for crypto market:
- Where are liquidation zones? (in crypto liquidations can be very sharp)
- What levels can trigger cascade liquidations? (crypto markets are more prone to cascades)
- What scenarios can lead to "squeeze"? (long squeeze or short squeeze)
- Liquidation levels based on leverage and OI

5. Alpha Setups: Menu of Hypotheses

Suggest 2-3 trading hypotheses for crypto futures:
A - Trend Following (important in crypto due to strong trends)
B - Mean Reversion (works on volatile crypto markets)
C - Microstructure Edge (based on funding/OI - especially effective in crypto)

For each hypothesis specify:
- Entry levels (specific prices)
- Stop loss (considering high crypto volatility)
- Take profit (realistic targets for crypto)
- Invalidation conditions
- Confidence level (0-1)

6. Risk Assessment

Assess crypto-specific risks:
- Maximum risk per trade (crypto can move 10-20% per day)
- Correlation with BTC and overall crypto market
- Potential catalysts (news, events, listings, forks)
- Gap risk and low liquidity (especially for altcoins)
- Cascade liquidation risk

7. Final Recommendation

Give clear recommendation for crypto futures:
- Action: BUY / SELL / HOLD / WAIT
- Position size (considering crypto volatility)
- Rationale (with crypto-specific considerations)
- Key levels to monitor
- Recommended leverage (for crypto usually 2-10x, no more)

Response format: structured, professional, with specific numbers and levels, adapted for crypto markets."""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional crypto trader-analyst with deep understanding of crypto futures markets (BTC, ETH, altcoins), funding rates, open interest and crypto market microstructure. Your analyses are accurate, structured and contain specific trading recommendations adapted for high volatility and crypto market specifics."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000,
                temperature=TEMPERATURE_ANALYSIS
            )
            analysis_text = completion.choices[0].message.content
            
            if db_service:
                try:
                    response_payload = {
                        "analysis_type": "market_report",
                        "symbol": symbol,
                        "analysis": analysis_text
                    }
                    db_service.save_ai_response(
                        request_type="market_analysis",
                        symbols=[symbol] if symbol else [],
                        response_data=response_payload,
                        prompt_text=prompt
                    )
                except Exception as save_error:
                    import logging
                    logging.getLogger(__name__).warning(f"Не удалось сохранить анализ AI: {save_error}")
            
            return analysis_text
        except Exception as e:
            print(f"Ошибка при обращении к AI: {e}")
            import traceback
            traceback.print_exc()
            return "Не удалось получить анализ от AI"
    
    def get_trading_advice(self, symbol, current_price, balance):
        """Get trading advice from AI"""
        prompt = f"""
        You are an experienced trader-analyst. Analyze the situation:
        
        Trading instrument: {symbol}
        Current price: {current_price}
        Available balance: {balance} USDT
        
        Give brief advice (2-3 sentences): should we open a position now? 
        If yes, which one (buy/sell) and why?
        """
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=300,
                temperature=TEMPERATURE_ADVICE
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Ошибка при получении совета от AI: {e}")
            return "Не удалось получить совет от AI"
    
    def analyze_market_for_trade_selection(self, market_data_list: List[Dict], existing_positions: Optional[List[Dict]] = None, balance: Optional[float] = None, db_service = None) -> Optional[Dict]:
        """
        AI-анализ для выбора лучшей монеты для торговли из списка кандидатов.
        
        Args:
            market_data_list: Список словарей с данными о монетах:
                [{"symbol": "BTCUSDT", "market_data": {...}, "score": 85.5, "data": {...}}, ...]
            existing_positions: Список существующих позиций для учета корреляции и диверсификации
        
        Returns:
            Dict с рекомендацией: {"recommended_symbol": "BTCUSDT", "recommended_side": "Long", "confidence": 0.85, "reasoning": "..."}
        """
        if not market_data_list:
            return None
        
        try:
            # Format existing positions info
            positions_info = ""
            liquidation_zones = []
            if existing_positions:
                active_positions = [
                    pos for pos in existing_positions 
                    if pos.get("symbol") and abs(float(pos.get("size", 0) or pos.get("qty", 0) or 0)) > 0.0001
                ]
                if active_positions:
                    positions_list = []
                    for pos in active_positions:
                        symbol = pos.get("symbol", "N/A")
                        side = pos.get("side", "N/A")
                        size = abs(float(pos.get("size", 0) or pos.get("qty", 0) or 0))
                        entry = pos.get("avgPrice", "N/A")
                        pnl = pos.get("unrealisedPnl", "N/A")
                        liq_price = pos.get("liqPrice") or pos.get("liquidationPrice")
                        if liq_price and liq_price != "N/A":
                            try:
                                liq_float = float(liq_price)
                                positions_list.append(f"  • {symbol}: {side.upper()} | Size: {size:.6f} | Entry: ${entry} | P&L: ${pnl} | Liq: ${liq_float:.2f}")
                                liquidation_zones.append({"symbol": symbol, "price": liq_float, "side": side})
                            except (ValueError, TypeError):
                                positions_list.append(f"  • {symbol}: {side.upper()} | Size: {size:.6f} | Entry: ${entry} | P&L: ${pnl}")
                        else:
                            positions_list.append(f"  • {symbol}: {side.upper()} | Size: {size:.6f} | Entry: ${entry} | P&L: ${pnl}")
                    
                    liq_info = ""
                    if liquidation_zones:
                        liq_list = [f"  • {z['symbol']}: ${z['price']:.2f} ({z['side'].upper()})" for z in liquidation_zones]
                        liq_info = f"\nLIQUIDATION ZONES (existing positions):\n{chr(10).join(liq_list)}\n"
                    
                    positions_info = f"""
CURRENT OPEN POSITIONS:
{chr(10).join(positions_list)}
{liq_info}
IMPORTANT: Consider correlation with existing positions. Avoid opening highly correlated positions (e.g., BTCUSDT and ETHUSDT have ~0.85 correlation). Prefer diversification across different sectors and directions. Be aware of liquidation zones - avoid opening positions too close to existing liquidation prices.
"""
            
            # Add context information (balance, time of day)
            from datetime import datetime
            current_time = datetime.utcnow()
            hour_utc = current_time.hour
            
            # ВРЕМЕННО: Используем дефолтные значения, пока база наполняется
            # Не используем данные из БД для анализа ликвидности
            liquidity_period = "MODERATE_LIQUIDITY"
            liquidity_analysis = ""
            
            # Используем простую эвристику на основе времени суток
            if 0 <= hour_utc < 4:
                liquidity_period = f"LOW_LIQUIDITY (hour {hour_utc} UTC) - be cautious, spreads may be wider"
            elif 8 <= hour_utc < 20:
                liquidity_period = f"HIGH_LIQUIDITY (hour {hour_utc} UTC) - optimal trading hours"
            else:
                liquidity_period = f"MODERATE_LIQUIDITY (hour {hour_utc} UTC)"
            
            # Временный комментарий о том, что БД не используется
            liquidity_analysis = f"""
NOTE: Using default liquidity analysis (database temporarily disabled while being populated).
Current time: {hour_utc} UTC
"""
            
            balance_info = ""
            if balance is not None:
                balance_info = f"\nACCOUNT BALANCE: ${balance:.2f} USDT\n"
            
            # Form prompt for AI
            prompt_parts = [
                "You are a professional crypto trader-analyst. Analyze the following coins and select ONE best for opening a position NOW.\n\n",
                f"CURRENT TIME: {current_time.strftime('%Y-%m-%d %H:%M UTC')} ({liquidity_period})\n",
                liquidity_analysis,
                balance_info,
                positions_info
            ]
            
            for i, item in enumerate(market_data_list, 1):
                symbol = item["symbol"]
                market_data = item["market_data"]
                score = item.get("score", 0)
                data = item.get("data", {})
                
                ticker = market_data.get('ticker', {})
                funding = market_data.get('funding', {})
                oi = market_data.get('open_interest', {})
                historical = market_data.get("historical") or {}
                order_book = market_data.get('order_book', {})
                candle_patterns = historical.get('candle_patterns', {})
                order_book_depth = historical.get('order_book_depth', {})
                news = market_data.get("news")
                
                current_price = float(ticker.get('last_price', 0)) if ticker.get('last_price') else data.get('current_price', 0)
                
                # Извлекаем все детальные данные
                ema_50 = historical.get('ema_50')
                ema_200 = historical.get('ema_200')
                vwap = historical.get('vwap')
                support_levels = historical.get('support_levels', [])
                resistance_levels = historical.get('resistance_levels', [])
                wick_analysis = candle_patterns.get('wick_analysis', {}) if candle_patterns else {}
                patterns = candle_patterns.get('patterns', []) if candle_patterns else []
                
                week_change = data.get("week_change", 0)
                day_change = data.get("day_change", data.get("change_24h", 0))
                range_width = data.get("range_width", 0)
                avg_hourly_volume = data.get("avg_hourly_volume", 0)

                prompt_parts.append(f"""
{i}. {symbol} (Score: {score:.1f})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRICE AND KEY METRICS:
- Current price: ${current_price}
- 24h change: {day_change:.2f}%
- 7d change: {week_change:.2f}%
- 7d range: {range_width:.4f}
- High 24h: ${historical.get('high_24h', 'N/A')}
- Low 24h: ${historical.get('low_24h', 'N/A')}
- Volatility: {data.get('volatility', 0):.2f}%
- 24h volume: {data.get('volume_24h', 0):,.0f}
- Average hourly volume: {avg_hourly_volume:,.0f}
- Funding Rate: {funding.get('funding_rate', 0) if funding else 0}
- Open Interest: {oi.get('open_interest', 0) if oi else 0}
- Liquidity (0-10): {data.get('liquidity_score', 0)}

TECHNICAL INDICATORS:
- EMA(50): ${ema_50 if ema_50 else 'N/A'} | EMA(200): ${ema_200 if ema_200 else 'N/A'}
- EMA Signal: {historical.get('ema_signal', 'N/A')} (BULLISH/BEARISH/NEUTRAL)
- VWAP: ${vwap if vwap else 'N/A'}
- VWAP deviation: {historical.get('vwap_distance', 0):.2f}%
- RSI(14): {historical.get('rsi', 'N/A')} ({historical.get('rsi_signal', 'N/A')}) (30=oversold, 70=overbought)
- ATR(14): ${historical.get('atr', 'N/A')} (Average True Range for stop loss calculation)
- MACD: {f"MACD={historical.get('macd', {}).get('macd', 'N/A')}, Signal={historical.get('macd', {}).get('signal', 'N/A')}, Histogram={historical.get('macd', {}).get('histogram', 'N/A')}, Signal={historical.get('macd', {}).get('macd_signal', 'N/A')}" if historical.get('macd') else 'N/A'}
- Bollinger Bands: {f"Upper=${historical.get('bollinger_bands', {}).get('upper_band', 'N/A')}, Middle=${historical.get('bollinger_bands', {}).get('middle_band', 'N/A')}, Lower=${historical.get('bollinger_bands', {}).get('lower_band', 'N/A')}, %B={historical.get('bollinger_bands', {}).get('percent_b', 'N/A')}, Position={historical.get('bollinger_bands', {}).get('band_position', 'N/A')}" if historical.get('bollinger_bands') else 'N/A'}
- Historical trend: {historical.get('historical_trend', 'N/A')}
- Market condition: {data.get('overbought_status', 'N/A')} (OVERBOUGHT/OVERSOLD/NEUTRAL)

SUPPORT AND RESISTANCE LEVELS:
- Support: {support_levels[:5] if support_levels else 'N/A'}
- Resistance: {resistance_levels[:5] if resistance_levels else 'N/A'}

SMART MONEY (WHALES):
- Sentiment: {historical.get('smart_money_bias', 'N/A')} (BULLISH/BEARISH/NEUTRAL)
- Net flow: {historical.get('smart_money_flow', 0):,.0f}$ (positive = buys, negative = sells)

CANDLESTICK PATTERNS:
- Detected patterns: {patterns if patterns else 'N/A'}
- Wick analysis:
  * Upper wicks: {wick_analysis.get('upper_wicks', 'N/A')}
  * Lower wicks: {wick_analysis.get('lower_wicks', 'N/A')}
  * Body to wick ratio: {wick_analysis.get('body_to_wick_ratio', 'N/A')}
  * Rejection levels: {wick_analysis.get('rejection_levels', 'N/A')}

ORDER BOOK DEPTH:
- Buy depth: {order_book_depth.get('buy_depth', 'N/A') if order_book_depth else 'N/A'}
- Sell depth: {order_book_depth.get('sell_depth', 'N/A') if order_book_depth else 'N/A'}
- Imbalance: {order_book_depth.get('imbalance', 'N/A') if order_book_depth else 'N/A'}
- Key support levels in order book: {order_book_depth.get('support_levels', [])[:3] if order_book_depth and order_book_depth.get('support_levels') else 'N/A'}
- Key resistance levels in order book: {order_book_depth.get('resistance_levels', [])[:3] if order_book_depth and order_book_depth.get('resistance_levels') else 'N/A'}

NEWS:
Sentiment: {news.get('sentiment', 'N/A') if news else 'N/A'}
Summary: {news.get('summary', 'No summary') if news else 'No news'}
News snippets:
{news.get('news_items', 'No news') if news else 'No news'}
""")
            
            prompt_parts.append("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECISION INSTRUCTIONS:

You are a professional crypto trader-analyst. Analyze ALL coins above and select ONE best for opening a position RIGHT NOW.

USE ALL INDICATORS FOR DECISION MAKING:

1. EMA(50/200) - determines trend:
   - If price above EMA50 and EMA50 above EMA200 → BULLISH (Long)
   - If price below EMA50 and EMA50 below EMA200 → BEARISH (Short)
   - EMA signal shows trend strength

2. VWAP - fair price:
   - If price above VWAP → Long possible
   - If price below VWAP → Short possible
   - Large VWAP deviation may indicate overbought/oversold

3. SUPPORT/RESISTANCE LEVELS - key for stop loss:
   - Stop loss should be BEYOND support level (for Long) or resistance (for Short)
   - Use nearest strong level as stop loss reference
   - Don't place stop too close to current price (consider volatility)

4. SMART MONEY - follow whales:
   - If Smart Money BULLISH and flow positive → Long
   - If Smart Money BEARISH and flow negative → Short
   - This is an important signal!

5. CANDLESTICK PATTERNS - show sentiment:
   - DOJI, HAMMER → possible reversal
   - MARUBOZU → strong trend
   - Wick analysis shows rejection levels

6. ORDER BOOK DEPTH - shows real liquidity:
   - High depth at level = strong support/resistance
   - Imbalance shows pressure direction

7. NEWS - emotional backdrop:
   - BULLISH news → Long
   - BEARISH news → Short

8. VOLATILITY - determines stop loss size:
   - High volatility → stop further from price
   - Low volatility → stop closer to price

9. RSI (Relative Strength Index) - momentum indicator:
   - RSI > 70 = OVERBOUGHT (risk for Long, opportunity for Short)
   - RSI < 30 = OVERSOLD (risk for Short, opportunity for Long)
   - RSI 30-70 = NEUTRAL zone
   - Use RSI to confirm entry direction and avoid overbought/oversold zones

10. ATR (Average True Range) - volatility measure:
    - ATR shows true market volatility (better than simple %)
    - For stop loss: use ATR * 2 (standard practice)
    - Higher ATR = wider stop loss needed
    - Lower ATR = tighter stop loss possible

11. MACD (Moving Average Convergence Divergence) - trend and momentum:
    - MACD line > Signal line = BULLISH momentum
    - MACD line < Signal line = BEARISH momentum
    - Histogram > 0 = strengthening trend
    - Histogram < 0 = weakening trend
    - MACD crossover (MACD crosses Signal) = potential trend change

12. BOLLINGER BANDS - volatility and extreme levels:
    - Price above upper band = OVERBOUGHT (potential reversal down)
    - Price below lower band = OVERSOLD (potential reversal up)
    - Price in middle = normal range
    - Narrow bands = low volatility (potential breakout)
    - Wide bands = high volatility (potential consolidation)
    - %B > 0.8 = near overbought, %B < 0.2 = near oversold

13. PORTFOLIO DIVERSIFICATION - consider existing positions:
    - If existing positions are shown above, avoid highly correlated coins
    - BTCUSDT and ETHUSDT have ~0.85 correlation (avoid both)
    - Prefer diversification: different sectors, different directions (Long/Short mix)
    - If all positions are Long, consider Short opportunities
    - If all positions are Short, consider Long opportunities

14. TIME OF DAY / LIQUIDITY PERIOD:
    - LOW_LIQUIDITY (00:00-04:00 UTC): Be cautious, wider spreads, higher slippage risk
    - HIGH_LIQUIDITY (08:00-20:00 UTC): Optimal trading hours, tighter spreads
    - MODERATE_LIQUIDITY: Normal trading conditions
    - Prefer entering positions during HIGH_LIQUIDITY periods when possible

15. LIQUIDATION ZONES:
    - If liquidation zones are shown above, these are prices where existing positions will be liquidated
    - Avoid opening new positions too close to these zones (risk of cascade liquidations)
    - Large liquidation zones can cause price volatility and slippage
    - Consider liquidation zones when setting stop loss levels

IMPORTANT: STOP LOSS AND TAKE PROFIT DEFINITION:

STOP LOSS should be:
- BEYOND nearest strong support level (for Long) or resistance (for Short)
- If ATR available: use entry_price ± (ATR * 2) as base, then adjust to nearest key level
- If ATR not available: use volatility-based calculation (not too close to avoid noise)
- Minimum distance: 0.5% of entry price
- Maximum distance: 5% of entry price (unless strong level requires more)
- Reasonable from risk-reward perspective

TAKE PROFIT should be:
- Target PnL: +0.5% GROSS profit (before commissions)
- Calculate: for Long: take_profit = entry_price * 1.005, for Short: take_profit = entry_price * 0.995
- But also consider nearest resistance levels (for Long) or support (for Short)
- Commissions will be deducted automatically, but target profit = 0.5% gross

CALCULATION EXAMPLE:
If entry_price = 86500 (Long):
- take_profit = 86500 * 1.00575 = 86997.375 (≈87000)
- stop_loss should be beyond support level, e.g. 86000
- Check: (87000 - 86500) / 86500 = 0.578% gross → 0.5% net profit ✅

Respond in JSON format:
{
  "recommended_symbol": "BTCUSDT",
  "recommended_side": "Long" or "Short",
  "entry_price": 86500.0,
  "stop_loss": 86000.0,
  "take_profit": 87000.0,
  "confidence": 0.85,
  "reasoning": "Detailed rationale: why this coin, why this side, why these stop and take (reference specific indicators: EMA, levels, Smart Money, etc.)",
  "missing_data": ["list of data missing for 100% confidence, e.g.: 'RSI indicator', 'MACD', 'more historical data', 'liquidity data on other exchanges', etc. If data is sufficient, specify empty array []"]
}
""")
            
            prompt = "\n".join(prompt_parts)
            
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional crypto trader-analyst. Your decisions are accurate and based on deep analysis. Always respond with valid JSON."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=1000,
                    temperature=TEMPERATURE_TRADE_PLAN,
                    response_format={"type": "json_object"}
                )
                
                response_text = completion.choices[0].message.content
                result = json.loads(response_text)
            except (APITimeoutError, TimeoutError) as e:
                import logging
                logging.getLogger(__name__).error(f"Таймаут при AI-анализе для выбора монеты: {e}")
                return None
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Ошибка при AI-анализе для выбора монеты: {e}")
                return None
            
            # Сохраняем ответ AI в БД (если db_service доступен)
            if db_service:
                try:
                    symbols_list = [item["symbol"] for item in market_data_list]
                    saved = db_service.save_ai_response(
                        request_type="trade_selection",
                        symbols=symbols_list,
                        response_data=result,
                        prompt_text=prompt
                    )
                    if saved:
                        import logging
                        logging.getLogger(__name__).info(f"✅ Сохранен AI ответ trade_selection для {result.get('recommended_symbol', 'N/A')}")
                    else:
                        import logging
                        logging.getLogger(__name__).warning(f"⚠️ Не удалось сохранить AI ответ trade_selection")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"❌ Ошибка при сохранении AI ответа trade_selection: {e}", exc_info=True)
            else:
                import logging
                logging.getLogger(__name__).warning(f"⚠️ db_service не доступен для сохранения trade_selection")
            
            # Валидация результата
            if result.get("recommended_symbol") in [item["symbol"] for item in market_data_list]:
                return result
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"AI вернул невалидный символ: {result.get('recommended_symbol')}")
                return None
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при AI-анализе для выбора монеты: {e}", exc_info=True)
            return None
    
    def analyze_asset_trade_plan(self, asset_entry: Dict, db_service = None) -> Optional[Dict]:
        """
        Получить торговый план (сторона, вход, SL/TP) для конкретной монеты.
        """
        try:
            symbol = asset_entry.get("symbol")
            market_data = asset_entry.get("market_data") or {}
            data = asset_entry.get("data") or {}
            score = asset_entry.get("score", 0)
            
            ticker = market_data.get("ticker") or {}
            funding = market_data.get("funding") or {}
            oi = market_data.get("open_interest") or {}
            historical = market_data.get("historical") or {}
            order_book = market_data.get("order_book") or {}
            news = market_data.get("news") or {}
            candle_patterns = historical.get("candle_patterns") or {}
            wick_analysis = candle_patterns.get("wick_analysis") or {}
            
            current_price = float(ticker.get("last_price") or data.get("current_price") or 0)
            prompt = f"""
Coin: {symbol}
Score: {score:.1f}
Current price: {current_price}
24h change: {float(ticker.get('change_24h', 0)) * 100:.2f}%
Volatility: {data.get('volatility', 0):.2f}%
24h volume: {data.get('volume_24h', 0):,.0f}
Liquidity: {data.get('liquidity_score', 0)}
Funding: {funding.get('funding_rate', 0) if funding else 0}
Open Interest: {oi.get('open_interest', 0) if oi else 0}
EMA signal: {historical.get('ema_signal')}
Smart Money: {historical.get('smart_money_bias')} / flow {historical.get('smart_money_flow', 0)}
Price vs VWAP: {historical.get('vwap_distance', 0)}
Supports: {historical.get('support_levels', [])[:3]}
Resistances: {historical.get('resistance_levels', [])[:3]}
Order book: bids {order_book.get('total_buy_qty')} / asks {order_book.get('total_sell_qty')}
News: {news.get('sentiment', 'N/A')} / {news.get('summary', 'no')}
Patterns: {candle_patterns.get('patterns', [])}
"""
            prompt += """
Form trading plan in JSON:
{
  "symbol": "...",
  "recommended_side": "Long|Short",
  "entry_price": 0.0,
  "stop_loss": 0.0,
  "take_profit": 0.0,
  "confidence": 0.0,
  "reasoning": "brief rationale"
}
Requirements:
- Use current levels and volatility
- Stop loss beyond nearest key level, consider volatility
- Take profit for ~0.5% gross profit or nearest strong level in trade direction
- If data insufficient, return null
"""
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an experienced crypto trader. Respond with valid JSON containing trading plan."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=600,
                    temperature=TEMPERATURE_TRADE_PLAN,
                    response_format={"type": "json_object"}
                )
                result = json.loads(completion.choices[0].message.content)
            except (APITimeoutError, TimeoutError) as e:
                import logging
                logging.getLogger(__name__).error(f"Таймаут при AI-анализе торгового плана для {asset_entry.get('symbol', 'UNKNOWN')}: {e}")
                return None
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Ошибка при AI-анализе торгового плана для {asset_entry.get('symbol', 'UNKNOWN')}: {e}")
                return None
            
            # Сохраняем ответ AI в БД
            if db_service and result:
                try:
                    symbol = asset_entry.get("symbol", "UNKNOWN")
                    saved = db_service.save_ai_response(
                        request_type="trade_plan",
                        symbols=[symbol],
                        response_data=result,
                        prompt_text=prompt
                    )
                    if saved:
                        import logging
                        logging.getLogger(__name__).info(f"✅ Сохранен AI ответ trade_plan для {symbol}")
                    else:
                        import logging
                        logging.getLogger(__name__).warning(f"⚠️ Не удалось сохранить AI ответ trade_plan для {symbol}")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"❌ Ошибка при сохранении AI ответа trade_plan для {asset_entry.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
            else:
                if not db_service:
                    import logging
                    logging.getLogger(__name__).warning(f"⚠️ db_service не доступен для сохранения trade_plan для {asset_entry.get('symbol', 'UNKNOWN')}")
            
            if result.get("symbol") and result.get("recommended_side"):
                return result
            return None
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"AI план для {asset_entry.get('symbol')}: {e}", exc_info=True)
            return None
    
    def analyze_trading_decision(self, prompt):
        """Анализ для принятия торгового решения (возвращает JSON)"""
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional trader-analyst specializing in futures markets. Your decisions are accurate, structured and contain specific trading recommendations in JSON format. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=1500,
                temperature=TEMPERATURE_TRADE_PLAN,
                response_format={"type": "json_object"}
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Ошибка при анализе торгового решения: {e}")
            import traceback
            traceback.print_exc()
            return None

