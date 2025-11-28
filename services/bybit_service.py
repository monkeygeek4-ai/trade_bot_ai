# Code review marker
from pybit.unified_trading import HTTP
import config
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class BybitService:
    def __init__(self, db_service=None):
        logger.info(f"Инициализация BybitService: testnet={config.BYBIT_TESTNET}")
        self.client = HTTP(
            testnet=config.BYBIT_TESTNET,
            api_key=config.BYBIT_API_KEY,
            api_secret=config.BYBIT_API_SECRET,
        )
        self.db_service = db_service  # Для сохранения ошибок
    
    def get_balance(self):
        """Получить баланс кошелька (фьючерсный счет)"""
        try:
            response = self.client.get_wallet_balance(
                accountType="UNIFIED"  # UNIFIED включает фьючерсы
            )
            
            # Логируем ответ для отладки
            if "retCode" not in response:
                print(f"Неожиданный формат ответа: {response}")
                return None
            
            if response["retCode"] != 0:
                error_msg = response.get("retMsg", "Unknown error")
                error_code = response.get("retCode", "N/A")
                logger.error(f"Ошибка Bybit API: {error_msg} (код: {error_code})")
                print(f"Ошибка Bybit API: {error_msg} (код: {error_code})")
                
                # Сохраняем ошибку в БД
                if self.db_service:
                    try:
                        self.db_service.save_api_error("get_balance", "N/A", str(error_code), error_msg, response)
                    except Exception:
                        pass
                
                # Детальная информация об ошибках
                if error_code == 401:
                    print("⚠️ Ошибка аутентификации (401):")
                    print("   - Проверьте правильность API ключей")
                    if config.BYBIT_TESTNET:
                        print("   - Убедитесь, что используете тестовые API ключи для testnet")
                    else:
                        print("   - Убедитесь, что используете production API ключи")
                    print("   - Проверьте разрешения API ключа (нужен доступ к чтению баланса)")
                elif error_code == 10003:
                    print("⚠️ Неверный API ключ")
                elif error_code == 10004:
                    print("⚠️ Неверная подпись запроса")
                
                return None
            
            if "result" not in response or "list" not in response["result"]:
                print(f"Неожиданная структура ответа: {response}")
                return None
            
            if not response["result"]["list"]:
                print("Список кошельков пуст")
                return None
            
            balance = response["result"]["list"][0].get("totalWalletBalance", "0")
            return balance
        except KeyError as e:
            print(f"Ошибка доступа к ключу в ответе: {e}")
            print(f"Ответ: {response if 'response' in locals() else 'N/A'}")
            return None
        except Exception as e:
            print(f"Ошибка при получении баланса: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_ticker(self, symbol="BTCUSDT"):
        """Получить текущую цену тикера с фьючерсного рынка"""
        try:
            # Увеличиваем таймаут для запросов
            response = self.client.get_tickers(
                category="linear",  # Фьючерсы вместо spot
                symbol=symbol,
                timeout=15  # Увеличиваем таймаут до 15 секунд
            )
            error_code = response.get("retCode", "N/A")
            
            # Успешный запрос (код 0) - не сохраняем в БД
            if error_code == 0:
                if response.get("result", {}).get("list"):
                    ticker = response["result"]["list"][0]
                    return {
                        "symbol": ticker["symbol"],
                        "last_price": ticker["lastPrice"],
                        "bid_price": ticker["bid1Price"],
                        "ask_price": ticker["ask1Price"],
                        "volume_24h": ticker["volume24h"],
                        "change_24h": ticker["price24hPcnt"],
                        "turnover_24h": ticker.get("turnover24h", "0"),
                        "high_price_24h": ticker.get("highPrice24h", "0"),
                        "low_price_24h": ticker.get("lowPrice24h", "0")
                    }
                return None
            
            # Обработка ошибок (код != 0)
            error_msg = response.get("retMsg", "Unknown error")
            
            # Не сохраняем ошибки для несуществующих символов
            if str(error_code) == "10001" or "symbol invalid" in error_msg.lower():
                logger.warning(f"Символ {symbol} недоступен на Bybit для фьючерсов (код: {error_code}) - пропускаю")
                return None
            
            # Сохраняем только реальные ошибки (не успешные запросы)
            if self.db_service:
                try:
                    self.db_service.save_api_error("get_ticker", symbol, str(error_code), error_msg, response)
                except Exception:
                    pass
            return None
        except Exception as e:
            error_msg = str(e)
            # Не сохраняем ошибки для несуществующих символов (чтобы не спамить БД)
            if "symbol invalid" in error_msg.lower() or "10001" in error_msg:
                logger.warning(f"Символ {symbol} недоступен на Bybit для фьючерсов - пропускаю")
                return None
            
            logger.error(f"Ошибка при получении тикера {symbol}: {e}")
            # Сохраняем только серьезные ошибки (не таймауты и не несуществующие символы)
            if self.db_service and "timeout" not in error_msg.lower() and "symbol invalid" not in error_msg.lower():
                try:
                    self.db_service.save_api_error("get_ticker", symbol, "EXCEPTION", error_msg)
                except Exception:
                    pass
            return None
    
    def get_funding_rate(self, symbol="BTCUSDT"):
        """Получить текущий funding rate для фьючерса"""
        try:
            response = self.client.get_funding_rate_history(
                category="linear",
                symbol=symbol,
                limit=1
            )
            if response["retCode"] == 0 and response["result"]["list"]:
                funding = response["result"]["list"][0]
                return {
                    "symbol": funding["symbol"],
                    "funding_rate": funding["fundingRate"],
                    "funding_rate_timestamp": funding.get("fundingRateTimestamp", "")
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении funding rate: {e}")
            return None
    
    def get_open_interest(self, symbol="BTCUSDT"):
        """Получить открытый интерес (OI) для фьючерса"""
        try:
            response = self.client.get_open_interest(
                category="linear",
                symbol=symbol,
                intervalTime="5min",
                limit=1
            )
            if response["retCode"] == 0 and response["result"]["list"]:
                oi = response["result"]["list"][0]
                return {
                    "symbol": oi.get("symbol", symbol),
                    "open_interest": oi.get("openInterest", "0"),
                    "timestamp": oi.get("timestamp", "")
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении open interest: {e}")
            return None
    
    def get_market_data_comprehensive(self, symbol="BTCUSDT"):
        """Получить комплексные данные о рынке для детального анализа"""
        try:
            ticker = self.get_ticker(symbol)
            funding = self.get_funding_rate(symbol)
            oi = self.get_open_interest(symbol)
            positions = self.get_positions()
            
            # Найти позицию по символу
            current_position = None
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("size", 0)) != 0:
                    current_position = {
                        "size": pos.get("size"),
                        "side": pos.get("side"),
                        "avg_price": pos.get("avgPrice"),
                        "unrealised_pnl": pos.get("unrealisedPnl"),
                        "leverage": pos.get("leverage"),
                        "mark_price": pos.get("markPrice"),
                        "liq_price": pos.get("liqPrice")
                    }
                    break
            
            return {
                "ticker": ticker,
                "funding": funding,
                "open_interest": oi,
                "current_position": current_position,
                "balance": self.get_balance()
            }
        except Exception as e:
            logger.error(f"Ошибка при получении комплексных данных: {e}")
            return None

    def get_kline(self, symbol="BTCUSDT", interval="60", limit=200, start_time=None, end_time=None):
        """
        Получить исторические свечи для указанного символа.
        
        Args:
            symbol: Символ торговой пары
            interval: Интервал свечей (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, "D", "M", "W")
            limit: Количество свечей (максимум 1000)
            start_time: Начальное время в миллисекундах (опционально)
            end_time: Конечное время в миллисекундах (опционально)
        
        Returns:
            Список свечей в формате [{"timestamp": ..., "open": ..., ...}, ...]
        """
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": min(max(limit, 1), 1000)
            }
            
            # Добавляем временные метки, если указаны
            if start_time:
                params["start"] = int(start_time)
            if end_time:
                params["end"] = int(end_time)
            
            response = self.client.get_kline(**params)
            if response.get("retCode") != 0:
                logger.error(f"Ошибка при получении свечей: {response.get('retMsg')}")
                return []

            candles = response.get("result", {}).get("list", [])
            formatted = []
            for candle in candles:
                # По спецификации pybit: [startTime, open, high, low, close, volume, turnover]
                formatted.append({
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                    "turnover": float(candle[6]) if len(candle) > 6 else 0.0,
                })
            # Свечи приходят от новой к старой, разворачиваем для удобства
            return list(reversed(formatted))
        except Exception as e:
            logger.error(f"Ошибка при получении исторических свечей {symbol}: {e}")
            return []
    
    def place_order(self, symbol, side, qty, order_type="Market", 
                   stop_loss=None, take_profit=None, reduce_only=False, prefer_maker=False):
        """
        Разместить ордер на фьючерсном рынке с защитными ордерами.
        """
        try:
            order_type = "Market"
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "reduceOnly": reduce_only
            }
            
            logger.info(f"Размещаю ордер: {symbol}, side={side}, qty={qty}, params={order_params}")
            response = self.client.place_order(**order_params)
            logger.info(f"Ответ API place_order: retCode={response.get('retCode')}, retMsg={response.get('retMsg')}")
            logger.debug(f"Полный ответ API: {response}")
            
            if response.get("retCode") != 0:
                error_msg = response.get("retMsg", "Неизвестная ошибка")
                error_code = response.get("retCode", "N/A")
                logger.error(f"❌ Ошибка при размещении ордера {symbol}: {error_msg} (код: {error_code})")
                logger.error(f"Параметры ордера: {order_params}")
                return {"error": f"{error_msg} (код: {error_code})"}
            
            order_result = response.get("result") or {}
            ret_ext_info = response.get("retExtInfo") or {}
            order_id = order_result.get("orderId") or ret_ext_info.get("orderId")
            order_status = order_result.get("orderStatus") or ret_ext_info.get("orderStatus") or "Filled"
            
            if not order_result and order_id:
                order_result = {
                    "orderId": order_id,
                    "orderStatus": order_status,
                    "orderType": order_type,
                    "side": side
                }
            
            logger.info(f"✅ Ордер размещен: {symbol}, side={side}, qty={qty}, orderId={order_id}, status={order_status}")
            
            if stop_loss or take_profit:
                tp_sl_ok = self._attach_tp_sl_with_retry(symbol, stop_loss, take_profit, order_type)
                order_result["tp_sl_attached"] = bool(tp_sl_ok)
            
            return order_result
        except Exception as e:
            logger.error(f"Ошибка при размещении ордера: {e}")
            return {"error": str(e)}

    def _attach_tp_sl_with_retry(self, symbol, stop_loss, take_profit, order_type):
        import time
        
        max_attempts = 5
        initial_wait = 1.0 if order_type == "Market" else 2.0
        time.sleep(initial_wait)
        
        for attempt in range(max_attempts):
            try:
                tp_sl_result = self.set_trading_stop(
                    symbol=symbol,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                if tp_sl_result:
                    logger.info(f"✅ TP/SL установлены для {symbol}: SL={stop_loss}, TP={take_profit}")
                    return True
                
                if attempt < max_attempts - 1:
                    logger.info(f"⏳ TP/SL не установлены, повтор через 1 сек (попытка {attempt + 1}/{max_attempts})")
                    time.sleep(1.0)
                else:
                    logger.warning(f"⚠️ Не удалось установить TP/SL для {symbol} после {max_attempts} попыток.")
            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.warning(f"⚠️ Ошибка при установке TP/SL (попытка {attempt + 1}/{max_attempts}): {e}, повторяю")
                    time.sleep(1.0)
                else:
                    logger.error(f"❌ Ошибка при установке TP/SL для {symbol} после {max_attempts} попыток: {e}")
        return False

    def get_order_book(self, symbol="BTCUSDT", limit=50):
        """Получить стакан цен по символу и оценить суммарные объёмы bid/ask."""
        try:
            response = self.client.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=min(max(limit, 1), 200)
            )
            if response.get("retCode") != 0:
                logger.error(f"Ошибка при получении стакана: {response.get('retMsg')}")
                return None

            result = response.get("result", {})
            bids_raw = result.get("b") or []
            asks_raw = result.get("a") or []
            list_raw = result.get("list") or []

            bids = []
            asks = []

            if list_raw:
                for level in list_raw:
                    price = float(level.get("price", 0))
                    size = float(level.get("size") or level.get("qty") or 0)
                    side = (level.get("side") or "").lower()
                    entry = {"price": price, "size": size}
                    if side in ("buy", "bid"):
                        bids.append(entry)
                    elif side in ("sell", "ask"):
                        asks.append(entry)
            else:
                for price, qty in bids_raw:
                    bids.append({"price": float(price), "size": float(qty)})
                for price, qty in asks_raw:
                    asks.append({"price": float(price), "size": float(qty)})

            total_buy = round(sum(level["size"] for level in bids), 6)
            total_sell = round(sum(level["size"] for level in asks), 6)
            
            # Анализ плотности стакана
            current_price = 0
            if bids and asks:
                current_price = (bids[0]['price'] + asks[0]['price']) / 2
            else:
                # Получаем текущую цену из ticker
                ticker = self.get_ticker(symbol)
                if ticker:
                    current_price = float(ticker.get('last_price', 0))
            
            # Плотность в зоне ±1% от текущей цены
            depth_analysis = self._analyze_order_book_depth(bids, asks, current_price) if current_price > 0 else {}
            
            return {
                "bids": bids,
                "asks": asks,
                "total_buy_qty": total_buy,
                "total_sell_qty": total_sell,
                "depth_analysis": depth_analysis
            }
        except Exception as e:
            logger.error(f"Ошибка при получении стакана {symbol}: {e}")
            return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Получить параметры лота для символа (minOrderQty и qtyStep) с Bybit.
        Используется для того, чтобы не ловить ошибки Qty invalid.
        """
        try:
            response = self.client.get_instruments_info(
                category="linear",
                symbol=symbol
            )
            if response.get("retCode") != 0:
                logger.error(
                    f"Ошибка get_instruments_info для {symbol}: "
                    f"{response.get('retMsg')} (код: {response.get('retCode')})"
                )
                return None

            instruments = (response.get("result") or {}).get("list") or []
            if not instruments:
                logger.warning(f"get_instruments_info: пустой список для {symbol}")
                return None

            lot_filter = instruments[0].get("lotSizeFilter") or {}
            try:
                min_qty = float(lot_filter.get("minOrderQty") or 0)
                qty_step = float(lot_filter.get("qtyStep") or 0)
            except (TypeError, ValueError):
                logger.warning(f"Не удалось распарсить lotSizeFilter для {symbol}: {lot_filter}")
                return None

            if min_qty <= 0 or qty_step <= 0:
                logger.warning(f"lotSizeFilter вернул некорректные значения для {symbol}: {lot_filter}")
                return None

            logger.info(
                f"Фильтры лота для {symbol}: min_qty={min_qty}, qty_step={qty_step}"
            )
            return {"min_qty": min_qty, "qty_step": qty_step}
        except Exception as e:
            logger.error(f"Ошибка при получении фильтров лота для {symbol}: {e}", exc_info=True)
            return None
    
    def _analyze_order_book_depth(self, bids: List[Dict], asks: List[Dict], current_price: float) -> Dict:
        """Анализ плотности стакана: распределение объемов по уровням."""
        if not current_price or not bids or not asks:
            return {
                "imbalance_ratio": 0.0,
                "support_levels": [],
                "resistance_levels": [],
                "depth_quality": "N/A",
                "liquidity_zones": []
            }
        
        # Анализ в зоне ±1% от текущей цены
        price_range = current_price * 0.01  # 1%
        
        # Объемы в зоне поддержки (bids)
        support_volume = sum(level["size"] for level in bids 
                           if abs(level["price"] - current_price) <= price_range)
        
        # Объемы в зоне сопротивления (asks)
        resistance_volume = sum(level["size"] for level in asks 
                              if abs(level["price"] - current_price) <= price_range)
        
        # Коэффициент дисбаланса (imbalance ratio)
        total_near_volume = support_volume + resistance_volume
        imbalance_ratio = (support_volume - resistance_volume) / total_near_volume if total_near_volume > 0 else 0.0
        
        # Ключевые уровни поддержки (большие объемы на бидах)
        support_levels = sorted(
            [level for level in bids if level["size"] > total_near_volume * 0.1],
            key=lambda x: x["size"],
            reverse=True
        )[:3]
        
        # Ключевые уровни сопротивления (большие объемы на асках)
        resistance_levels = sorted(
            [level for level in asks if level["size"] > total_near_volume * 0.1],
            key=lambda x: x["size"],
            reverse=True
        )[:3]
        
        # Оценка качества ликвидности
        if total_near_volume > current_price * 1000:  # Большой объем
            depth_quality = "ВЫСОКАЯ"
        elif total_near_volume > current_price * 100:
            depth_quality = "СРЕДНЯЯ"
        else:
            depth_quality = "НИЗКАЯ"
        
        # Зоны ликвидности (скопления ордеров)
        liquidity_zones = []
        for level in bids[:10] + asks[:10]:
            if level["size"] > total_near_volume * 0.05:
                liquidity_zones.append({
                    "price": level["price"],
                    "size": level["size"],
                    "distance_pct": abs((level["price"] - current_price) / current_price * 100)
                })
        
        return {
            "imbalance_ratio": round(imbalance_ratio, 4),  # >0 = больше поддержки, <0 = больше сопротивления
            "support_volume": round(support_volume, 2),
            "resistance_volume": round(resistance_volume, 2),
            "support_levels": [{"price": l["price"], "size": l["size"]} for l in support_levels],
            "resistance_levels": [{"price": l["price"], "size": l["size"]} for l in resistance_levels],
            "depth_quality": depth_quality,
            "liquidity_zones": liquidity_zones[:5]  # Топ-5 зон
        }

    def get_whale_trades(self, symbol="BTCUSDT", notional_threshold=50000, limit=200):
        """Получить информацию о крупных сделках (китовый поток)."""
        try:
            response = self.client.get_public_trade(
                category="linear",
                symbol=symbol,
                limit=min(max(limit, 1), 1000)
            )
            if response.get("retCode") != 0:
                logger.error(f"Ошибка при получении трейдов: {response.get('retMsg')}")
                return {}

            trades = response.get("result", {}).get("list", [])
            whales = []
            buy_notional = sell_notional = 0.0

            for trade in trades:
                side = (trade.get("side") or "").capitalize()
                price = float(trade.get("price") or trade.get("execPrice") or 0)
                qty = float(trade.get("size") or trade.get("execQty") or 0)
                notional = price * qty
                if side == "Buy":
                    buy_notional += notional
                elif side == "Sell":
                    sell_notional += notional

                if notional >= notional_threshold:
                    whales.append({
                        "side": side or "N/A",
                        "price": price,
                        "qty": qty,
                        "notional": round(notional, 2),
                        "timestamp": trade.get("time") or trade.get("tradeTime")
                    })

            net_flow = buy_notional - sell_notional
            bias = "BULLISH" if net_flow > notional_threshold else "BEARISH" if net_flow < -notional_threshold else "NEUTRAL"

            return {
                "total_buy": round(buy_notional, 2),
                "total_sell": round(sell_notional, 2),
                "net_flow": round(net_flow, 2),
                "bias": bias,
                "top_trades": whales[:5]
            }
        except AttributeError:
            logger.warning("Клиент pybit не поддерживает get_public_trade — пропускаю smart money анализ")
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении крупных сделок {symbol}: {e}")
            return {}
    
    def place_conditional_order(self, symbol, side, qty, trigger_price, 
                               order_type="Market", reduce_only=False):
        """Разместить условный ордер (стоп-лосс или тейк-профит) - УСТАРЕЛО, используйте set_trading_stop"""
        # Этот метод больше не используется, вместо него используется set_trading_stop
        logger.warning(f"place_conditional_order устарел, используйте set_trading_stop для {symbol}")
        return None
    
    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None, position_idx=0):
        """
        Установить стоп-лосс и/или тейк-профит для существующей позиции
        
        Args:
            symbol: Символ монеты (например, "BTCUSDT")
            stop_loss: Цена стоп-лосса (опционально)
            take_profit: Цена тейк-профита (опционально)
            position_idx: Индекс позиции (0 = односторонний режим, 1 = хеджирование Buy, 2 = хеджирование Sell)
        
        Returns:
            Dict с результатом операции или None при ошибке
        """
        try:
            # Если не указаны ни SL, ни TP, ничего не делаем
            if not stop_loss and not take_profit:
                logger.warning(f"Не указаны ни стоп-лосс, ни тейк-профит для {symbol}")
                return None
            
            params = {
                "category": "linear",
                "symbol": symbol,
                "positionIdx": position_idx
            }
            
            if stop_loss:
                params["stopLoss"] = str(stop_loss)
            
            if take_profit:
                params["takeProfit"] = str(take_profit)
            
            logger.info(f"Устанавливаю TP/SL для {symbol}: SL={stop_loss}, TP={take_profit}")
            response = self.client.set_trading_stop(**params)
            
            if response.get("retCode") == 0:
                logger.info(f"✅ TP/SL успешно установлены для {symbol}: SL={stop_loss}, TP={take_profit}")
                return response.get("result")
            else:
                error_msg = response.get("retMsg", "Неизвестная ошибка")
                error_code = response.get("retCode", "N/A")
                logger.error(f"❌ Ошибка при установке TP/SL для {symbol}: {error_msg} (код: {error_code})")
                logger.debug(f"Полный ответ API: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при установке TP/SL для {symbol}: {e}", exc_info=True)
            return None
    
    def update_stop_loss(self, symbol, stop_loss_price):
        """Обновить стоп-лосс для позиции"""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("size", 0) or 0) != 0:
                    # Устанавливаем стоп-лосс через set_trading_stop
                    return self.set_trading_stop(
                        symbol=symbol,
                        stop_loss=stop_loss_price
                    )
            return None
        except Exception as e:
            logger.error(f"Ошибка при обновлении стоп-лосса: {e}")
            return None
    
    def update_take_profit(self, symbol, take_profit_price):
        """Обновить тейк-профит для позиции"""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("size", 0) or 0) != 0:
                    # Устанавливаем тейк-профит через set_trading_stop
                    return self.set_trading_stop(
                        symbol=symbol,
                        take_profit=take_profit_price
                    )
            return None
        except Exception as e:
            logger.error(f"Ошибка при обновлении тейк-профита: {e}")
            return None
    
    def update_tp_sl(self, symbol, stop_loss_price=None, take_profit_price=None):
        """
        Обновить стоп-лосс и/или тейк-профит для позиции
        
        Args:
            symbol: Символ монеты
            stop_loss_price: Новый уровень стоп-лосса (опционально)
            take_profit_price: Новый уровень тейк-профита (опционально)
        
        Returns:
            Dict с результатами обновления
        """
        results = {
            "stop_loss": None,
            "take_profit": None,
            "errors": []
        }
        
        try:
            positions = self.get_positions()
            position = None
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("size", 0) or 0) != 0:
                    position = pos
                    break
            
            if not position:
                results["errors"].append(f"Позиция по {symbol} не найдена")
                return results
            
            size = abs(float(position.get("size", 0)))
            position_side = position.get("side", "")
            
            # Отменяем все существующие TP/SL ордера для этой позиции
            try:
                self.client.cancel_all_orders(category="linear", symbol=symbol, orderFilter="tpslOrder")
                logger.info(f"Отменены существующие TP/SL ордера для {symbol}")
            except Exception as e:
                logger.warning(f"Не удалось отменить существующие TP/SL ордера: {e}")
            
            # Устанавливаем TP/SL через set_trading_stop (правильный способ)
            try:
                tp_sl_result = self.set_trading_stop(
                    symbol=symbol,
                    stop_loss=stop_loss_price,
                    take_profit=take_profit_price
                )
                if tp_sl_result:
                    if stop_loss_price:
                        results["stop_loss"] = stop_loss_price
                        logger.info(f"✅ Стоп-лосс обновлен для {symbol}: ${stop_loss_price}")
                    if take_profit_price:
                        results["take_profit"] = take_profit_price
                        logger.info(f"✅ Тейк-профит обновлен для {symbol}: ${take_profit_price}")
                else:
                    # Если API вернул пустой результат, но в самой позиции уже есть stopLoss/takeProfit,
                    # считаем это успехом (Bybit часто отвечает 'ничего не изменилось').
                    current_sl = position.get("stopLoss")
                    current_tp = position.get("takeProfit")
                    if (stop_loss_price and current_sl) or (take_profit_price and current_tp):
                        if stop_loss_price and current_sl:
                            results["stop_loss"] = float(current_sl)
                        if take_profit_price and current_tp:
                            results["take_profit"] = float(current_tp)
                        logger.info(
                            f"ℹ️ TP/SL для {symbol} уже установлены на бирже "
                            f"(SL={current_sl}, TP={current_tp}), изменений не требуется."
                        )
                    else:
                        if stop_loss_price:
                            results["errors"].append("Не удалось обновить стоп-лосс")
                        if take_profit_price:
                            results["errors"].append("Не удалось обновить тейк-профит")
            except Exception as e:
                error_msg = str(e)
                results["errors"].append(f"Ошибка при обновлении TP/SL: {error_msg}")
                logger.error(f"Ошибка при обновлении TP/SL для {symbol}: {e}")
            
            return results
        except Exception as e:
            logger.error(f"Ошибка при обновлении TP/SL для {symbol}: {e}")
            results["errors"].append(f"Общая ошибка: {str(e)}")
            return results
    
    def partial_close_position(self, symbol, close_percent=0.5):
        """Частично закрыть позицию"""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos.get("symbol") == symbol and float(pos.get("size", 0)) != 0:
                    size = float(pos.get("size", 0))
                    close_size = abs(size) * close_percent
                    side = "Sell" if size > 0 else "Buy"
                    
                    return self.place_order(
                        symbol=symbol,
                        side=side,
                        qty=close_size,
                        order_type="Market",
                        reduce_only=True
                    )
            return None
        except Exception as e:
            logger.error(f"Ошибка при частичном закрытии позиции: {e}")
            return None
    
    def close_all_positions(self):
        """Закрыть все открытые позиции"""
        try:
            positions = self.get_positions()
            closed = []
            errors = []
            
            for pos in positions:
                symbol = pos.get("symbol")
                size = float(pos.get("size", 0) or 0)
                
                if abs(size) < 0.001:  # Пропускаем пустые позиции
                    continue
                
                try:
                    # Логируем все данные позиции для диагностики
                    position_side = pos.get("side", "N/A")
                    position_size = pos.get("size", "N/A")
                    logger.info(f"Позиция {symbol}: size={size}, side={position_side}, raw_size={position_size}")
                    
                    # ВАЖНО: Bybit возвращает size всегда положительным!
                    # Тип позиции определяется полем "side":
                    # - side="Buy" → Long позиция → закрываем продажей (Sell)
                    # - side="Sell" → Short позиция → закрываем покупкой (Buy)
                    
                    # Определяем тип позиции по полю side из API
                    position_side_normalized = (position_side or "").capitalize()
                    
                    if position_side_normalized == "Buy":
                        # Long позиция - закрываем продажей
                        close_side = "Sell"
                        pos_type = "Long"
                    elif position_side_normalized == "Sell":
                        # Short позиция - закрываем покупкой
                        close_side = "Buy"
                        pos_type = "Short"
                    else:
                        # Если side не указан, определяем по размеру (fallback)
                        # Но это не должно происходить в нормальных условиях
                        logger.warning(f"Позиция {symbol}: side не указан ({position_side}), используем fallback")
                        if size > 0:
                            close_side = "Sell"
                            pos_type = "Long"
                        elif size < 0:
                            close_side = "Buy"
                            pos_type = "Short"
                        else:
                            continue  # size = 0, пропускаем
                    
                    qty = abs(size)
                    
                    logger.info(f"Закрытие {symbol}: позиция={pos_type}, qty={qty}, close_side={close_side}")
                    
                    # Закрываем позицию рыночным ордером
                    order_params = {
                        "category": "linear",
                        "symbol": symbol,
                        "side": close_side,
                        "orderType": "Market",
                        "qty": str(qty),
                        "reduceOnly": True
                    }
                    
                    logger.info(f"Отправка запроса на закрытие: {order_params}")
                    response = self.client.place_order(**order_params)
                    
                    if response.get("retCode") == 0:
                        closed.append({
                            "symbol": symbol,
                            "size": qty,
                            "side": pos_type
                        })
                        logger.info(f"Позиция {symbol} закрыта: {qty} ({pos_type})")
                    else:
                        error_msg = response.get("retMsg", "Неизвестная ошибка")
                        errors.append(f"{symbol}: {error_msg}")
                        logger.error(f"Ошибка при закрытии {symbol}: {error_msg}")
                        
                except Exception as e:
                    error_str = str(e)
                    errors.append(f"{symbol}: {error_str}")
                    logger.error(f"Ошибка при закрытии позиции {symbol}: {e}", exc_info=True)
            
            return {
                "closed": closed,
                "errors": errors,
                "total_closed": len(closed)
            }
        except Exception as e:
            logger.error(f"Ошибка при закрытии всех позиций: {e}", exc_info=True)
            return {"closed": [], "errors": [str(e)], "total_closed": 0}
    
    def get_positions(self):
        """Получить открытые позиции на фьючерсном рынке"""
        try:
            # Пробуем разные варианты запроса
            # Вариант 1: с settleCoin
            response = self.client.get_positions(
                category="linear",
                settleCoin="USDT"
            )
            
            logger.info(f"Ответ API get_positions: retCode={response.get('retCode')}, retMsg={response.get('retMsg')}")
            logger.info(f"Полный ответ API (первые 500 символов): {str(response)[:500]}")
            
            if response.get("retCode") == 0:
                positions = response.get("result", {}).get("list", [])
                logger.info(f"Получено позиций от Bybit API (вариант 1): {len(positions)}")
                
                # Если позиций нет, пробуем без settleCoin
                if len(positions) == 0:
                    logger.info("Пробую получить позиции без settleCoin...")
                    try:
                        response2 = self.client.get_positions(category="linear")
                        logger.info(f"Ответ API (вариант 2): retCode={response2.get('retCode')}, retMsg={response2.get('retMsg')}")
                        if response2.get("retCode") == 0:
                            positions = response2.get("result", {}).get("list", [])
                            logger.info(f"Получено позиций от Bybit API (вариант 2): {len(positions)}")
                            if positions:
                                logger.info(f"Полный ответ API (вариант 2): {str(response2)[:500]}")
                    except Exception as e2:
                        logger.warning(f"Ошибка при варианте 2: {e2}")
                
                # Если позиций нет, пробуем получить по конкретным символам
                if len(positions) == 0:
                    logger.info("Пробую получить позиции по популярным символам...")
                    popular_symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT",
                                     "AVAXUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT"]
                    for symbol in popular_symbols:
                        try:
                            response3 = self.client.get_positions(
                                category="linear",
                                symbol=symbol,
                                settleCoin="USDT"
                            )
                            if response3.get("retCode") == 0:
                                positions3 = response3.get("result", {}).get("list", [])
                                if positions3:
                                    for pos in positions3:
                                        size_val = pos.get("size", "0")
                                        try:
                                            size_float = float(size_val) if size_val and str(size_val) != "N/A" else 0
                                        except (ValueError, TypeError):
                                            size_float = 0
                                        if abs(size_float) > 0.0001:
                                            # Проверяем, нет ли уже такой позиции
                                            if not any(p.get("symbol") == pos.get("symbol") for p in positions):
                                                positions.append(pos)
                                                logger.info(f"✅ Найдена позиция {symbol}: size={size_float}, side={pos.get('side')}")
                        except Exception as e3:
                            pass  # Игнорируем ошибки для отдельных символов
                
                # Логируем все позиции для диагностики
                if positions:
                    logger.info(f"✅ ИТОГО найдено позиций: {len(positions)}")
                    for pos in positions:
                        symbol = pos.get("symbol", "N/A")
                        size = pos.get("size", "N/A")
                        side = pos.get("side", "N/A")
                        avg_price = pos.get("avgPrice", "N/A")
                        logger.info(f"Позиция: {symbol}, size={size}, side={side}, avgPrice={avg_price}")
                else:
                    logger.warning("⚠️ API вернул пустой список позиций после всех попыток")
                    logger.info(f"Структура ответа result: {response.get('result', {})}")
                    logger.info("💡 Проверьте: 1) Тип аккаунта (UNIFIED/DERIVATIVES), 2) Тестовая/основная сеть, 3) Права API ключа")
                
                return positions
            else:
                error_msg = response.get("retMsg", "Неизвестная ошибка")
                logger.warning(f"Bybit API вернул ошибку при получении позиций: {error_msg}, код: {response.get('retCode')}")
                logger.info(f"Полный ответ API при ошибке: {response}")
                return []
        except Exception as e:
            logger.error(f"Ошибка при получении позиций: {e}", exc_info=True)
            return []

