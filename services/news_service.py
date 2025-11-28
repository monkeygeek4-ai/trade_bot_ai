"""
Сервис для получения новостей и анализа эмоционального фона рынка через Perplexity API
"""
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from perplexity import Perplexity
    PERPLEXITY_AVAILABLE = True
except ImportError:
    PERPLEXITY_AVAILABLE = False
    logger.warning("Perplexity SDK не установлен. Установите: pip install perplexityai")


class NewsService:
    def __init__(self, api_key: Optional[str] = None):
        if not PERPLEXITY_AVAILABLE:
            raise ImportError("Perplexity SDK не установлен. Установите: pip install perplexityai")
        
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError("PERPLEXITY_API_KEY не установлен")
        
        self.client = Perplexity(api_key=self.api_key)
        
        # Доверенные источники для крипто-новостей
        self.crypto_news_sources = [
            "coindesk.com",
            "cointelegraph.com",
            "theblock.co",
            "decrypt.co",
            "cryptonews.com",
            "bitcoinmagazine.com",
            "crypto.news",
            "ru.investing.com"
        ]
    
    def get_crypto_news(self, symbol: str = "BTC", max_results: int = 10) -> List[Dict]:
        """
        Получить последние новости о криптовалюте
        
        Args:
            symbol: Символ криптовалюты (BTC, ETH, etc.)
            max_results: Максимальное количество результатов
        
        Returns:
            Список новостей
        """
        try:
            # Формируем запрос для поиска новостей
            query = f"{symbol} cryptocurrency news today latest updates market analysis"
            
            # Ищем новости с фильтром по крипто-источникам
            search = self.client.search.create(
                query=query,
                search_domain_filter=self.crypto_news_sources,
                max_results=max_results,
                max_tokens_per_page=1024
            )
            
            news_list = []
            for result in search.results:
                news_list.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet[:500] if hasattr(result, 'snippet') else "",
                    "date": getattr(result, 'date', None),
                    "source": self._extract_domain(result.url)
                })
            
            return news_list
        except Exception as e:
            logger.error(f"Ошибка при получении новостей для {symbol}: {e}")
            return []
    
    def get_market_sentiment(self, symbols: List[str] = None) -> Dict:
        """
        Получить общий эмоциональный фон рынка на основе новостей
        
        Args:
            symbols: Список символов для анализа (по умолчанию BTC, ETH)
        
        Returns:
            Словарь с анализом эмоционального фона
        """
        if symbols is None:
            symbols = ["BTC", "ETH"]
        
        try:
            # Общий запрос о рынке криптовалют
            query = "cryptocurrency market sentiment today bullish bearish news analysis"
            
            search = self.client.search.create(
                query=query,
                search_domain_filter=self.crypto_news_sources,
                max_results=15,
                max_tokens_per_page=1536
            )
            
            # Анализируем новости для определения настроения
            all_news = []
            for result in search.results:
                all_news.append({
                    "title": result.title,
                    "snippet": result.snippet[:500] if hasattr(result, 'snippet') else "",
                    "url": result.url,
                    "source": getattr(result, "source", ""),
                    "published_at": getattr(result, "published_at", "")
                })
            
            # Анализируем эмоциональный фон
            sentiment = self._analyze_sentiment(all_news)
            
            return {
                "sentiment": sentiment,
                "news_count": len(all_news),
                "news": all_news[:5],  # Топ-5 новостей
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Ошибка при анализе настроения рынка: {e}")
            return {
                "sentiment": "NEUTRAL",
                "news_count": 0,
                "news": [],
                "timestamp": datetime.now().isoformat()
            }
    
    def get_symbol_specific_news(self, symbol: str, max_results: int = 5) -> Dict:
        """
        Получить новости по конкретному символу с анализом
        
        Args:
            symbol: Символ (BTC, ETH, etc.)
            max_results: Максимальное количество результатов
        
        Returns:
            Словарь с новостями и анализом
        """
        try:
            # Получаем новости
            news = self.get_crypto_news(symbol, max_results)
            
            if not news:
                return {
                    "symbol": symbol,
                    "sentiment": "NEUTRAL",
                    "news": [],
                    "summary": "Новости не найдены"
                }
            
            # Анализируем настроение на основе новостей
            sentiment = self._analyze_sentiment(news)
            
            # Формируем краткое резюме
            summary = self._generate_summary(news, sentiment)
            
            return {
                "symbol": symbol,
                "sentiment": sentiment,
                "news": news,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Ошибка при получении новостей для {symbol}: {e}")
            return {
                "symbol": symbol,
                "sentiment": "NEUTRAL",
                "news": [],
                "summary": f"Ошибка: {str(e)}"
            }
    
    def _analyze_sentiment(self, news_list: List[Dict]) -> str:
        """
        Анализировать эмоциональный фон на основе новостей
        
        Returns:
            "BULLISH", "BEARISH", или "NEUTRAL"
        """
        if not news_list:
            return "NEUTRAL"
        
        # Ключевые слова для определения настроения
        bullish_keywords = [
            "surge", "rally", "bullish", "gains", "up", "rise", "growth",
            "adoption", "institutional", "breakthrough", "positive",
            "вырос", "рост", "ралли", "бычий", "позитивный"
        ]
        
        bearish_keywords = [
            "crash", "drop", "bearish", "decline", "down", "fall", "loss",
            "concern", "warning", "risk", "negative", "correction",
            "упал", "падение", "медвежий", "негативный", "риск"
        ]
        
        bullish_score = 0
        bearish_score = 0
        
        for news_item in news_list:
            text = (news_item.get("title", "") + " " + news_item.get("snippet", "")).lower()
            
            for keyword in bullish_keywords:
                if keyword in text:
                    bullish_score += 1
            
            for keyword in bearish_keywords:
                if keyword in text:
                    bearish_score += 1
        
        # Определяем настроение
        if bullish_score > bearish_score * 1.5:
            return "BULLISH"
        elif bearish_score > bullish_score * 1.5:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _generate_summary(self, news_list: List[Dict], sentiment: str) -> str:
        """Сгенерировать краткое резюме новостей"""
        if not news_list:
            return "Новости не найдены"
        
        sentiment_emoji = {
            "BULLISH": "📈",
            "BEARISH": "📉",
            "NEUTRAL": "➡️"
        }
        
        emoji = sentiment_emoji.get(sentiment, "➡️")
        
        summary = f"{emoji} Настроение рынка: {sentiment}\n\n"
        summary += f"Найдено новостей: {len(news_list)}\n\n"
        summary += "Ключевые новости:\n"
        
        for i, news in enumerate(news_list[:3], 1):
            summary += f"{i}. {news.get('title', 'Без заголовка')}\n"
            if news.get('snippet'):
                summary += f"   {news['snippet'][:100]}...\n"
        
        return summary
    
    def _extract_domain(self, url: str) -> str:
        """Извлечь домен из URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return url
    
    def get_trading_news_context(self, symbol: str) -> Dict:
        """
        Получить новостной контекст для торговых решений
        
        Args:
            symbol: Символ для анализа
        
        Returns:
            Словарь с новостным контекстом
        """
        try:
            # Получаем новости по символу
            symbol_news = self.get_symbol_specific_news(symbol, max_results=5)
            
            # Получаем общий фон рынка
            market_sentiment = self.get_market_sentiment([symbol])
            
            return {
                "symbol": symbol,
                "symbol_sentiment": symbol_news.get("sentiment", "NEUTRAL"),
                "market_sentiment": market_sentiment.get("sentiment", "NEUTRAL"),
                "symbol_news": symbol_news.get("news", []),
                "market_news": market_sentiment.get("news", []),
                "summary": symbol_news.get("summary", ""),
                "recommendation": self._generate_trading_recommendation(
                    symbol_news.get("sentiment", "NEUTRAL"),
                    market_sentiment.get("sentiment", "NEUTRAL")
                )
            }
        except Exception as e:
            logger.error(f"Ошибка при получении новостного контекста: {e}")
            return {
                "symbol": symbol,
                "symbol_sentiment": "NEUTRAL",
                "market_sentiment": "NEUTRAL",
                "recommendation": "Не удалось получить новостной контекст"
            }
    
    def _generate_trading_recommendation(self, symbol_sentiment: str, market_sentiment: str) -> str:
        """Сгенерировать торговую рекомендацию на основе новостного фона"""
        if symbol_sentiment == "BULLISH" and market_sentiment == "BULLISH":
            return "✅ Сильный бычий фон - рассмотреть лонг позиции"
        elif symbol_sentiment == "BEARISH" and market_sentiment == "BEARISH":
            return "⚠️ Сильный медвежий фон - рассмотреть шорт позиции или ожидание"
        elif symbol_sentiment == "BULLISH" and market_sentiment == "NEUTRAL":
            return "📈 Позитивный фон по активу при нейтральном рынке - осторожный лонг"
        elif symbol_sentiment == "BEARISH" and market_sentiment == "NEUTRAL":
            return "📉 Негативный фон по активу - избегать лонгов"
        elif symbol_sentiment == "NEUTRAL" and market_sentiment == "BULLISH":
            return "➡️ Нейтральный фон актива при бычьем рынке - следовать тренду"
        elif symbol_sentiment == "NEUTRAL" and market_sentiment == "BEARISH":
            return "➡️ Нейтральный фон актива при медвежьем рынке - осторожность"
        else:
            return "➡️ Смешанные сигналы - требуется дополнительный анализ"

