// Главный JavaScript файл для мониторинга

let updateInterval = null;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    loadAllData();
    
    // Обновление позиций каждые 5 секунд (реальные цены)
    positionsUpdateInterval = setInterval(loadPositions, 5000);
    
    // Обновление остальных данных каждые 30 секунд
    updateInterval = setInterval(() => {
        loadStats();
        loadTrades();
        loadAIResponses();
        loadErrors();
    }, 30000);
    
    // Обработчики фильтров по ботам
    document.querySelectorAll('.bot-filter').forEach(button => {
        button.addEventListener('click', function() {
            document.querySelectorAll('.bot-filter').forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            const botFilter = this.getAttribute('data-bot');
            tradesCurrentPage = 1; // Сбрасываем на первую страницу при смене фильтра
            loadTrades(botFilter, 1);
        });
    });
});

// Загрузка всех данных
async function loadAllData() {
    try {
        await Promise.all([
            loadStats(),
            loadPositions(),
            loadTrades(),
            loadAIResponses(),
            loadErrors()
        ]);
        
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString('ru-RU');
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
    }
}

// Загрузка статистики
async function loadStats() {
    try {
        const response = await fetch('api.php?action=stats');
        const data = await response.json();
        
        if (data.stats) {
            const stats = data.stats;
            
            // Общая статистика
            if (stats.trades_24h) {
                document.getElementById('stat-total-trades').textContent = stats.trades_24h.total || 0;
                document.getElementById('stat-winning').textContent = stats.trades_24h.winning || 0;
                document.getElementById('stat-losing').textContent = stats.trades_24h.losing || 0;
                document.getElementById('stat-winrate').textContent = 
                    (stats.trades_24h.win_rate || 0).toFixed(1) + '%';
                
                const totalPnl = stats.trades_24h.total_pnl || 0;
                const avgPnl = stats.trades_24h.avg_pnl || 0;
                
                document.getElementById('stat-total-pnl').textContent = 
                    formatNumber(totalPnl) + ' USDT';
                document.getElementById('stat-total-pnl').className = 
                    'stat-value ' + (totalPnl >= 0 ? 'positive' : 'negative');
                
                document.getElementById('stat-avg-pnl').textContent = 
                    formatNumber(avgPnl) + ' USDT';
                document.getElementById('stat-avg-pnl').className = 
                    'stat-value ' + (avgPnl >= 0 ? 'positive' : 'negative');
            }
            
            if (stats.ai_24h) {
                document.getElementById('stat-ai-responses').textContent = stats.ai_24h.total_responses || 0;
            }
            
            document.getElementById('stat-errors').textContent = stats.errors_24h || 0;
            
            // Статистика по ботам
            if (stats.bots) {
                const botsContainer = document.getElementById('bots-stats-container');
                if (botsContainer) {
                    botsContainer.innerHTML = '';
                    
                    // Сортируем ботов: main первый, потом iliya
                    const botNames = Object.keys(stats.bots).sort((a, b) => {
                        if (a === 'main') return -1;
                        if (b === 'main') return 1;
                        return a.localeCompare(b);
                    });
                    
                    botNames.forEach(botName => {
                        const botStats = stats.bots[botName];
                        const botDisplayName = botName === 'iliya' ? 'Iliya' : 'Main';
                        const botBadgeClass = botName === 'iliya' ? 'bot-iliya' : 'bot-main';
                        
                        const totalPnl = botStats.total_pnl || 0;
                        const avgPnl = botStats.avg_pnl || 0;
                        const winRate = botStats.win_rate || 0;
                        
                        const card = document.createElement('div');
                        card.style.cssText = 'background: #ffffff; border: 2px solid #e5e7eb; border-radius: 12px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);';
                        card.innerHTML = `
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 2px solid #e5e7eb;">
                                <h4 style="margin: 0; font-size: 18px; font-weight: bold; color: #374151;">Бот: <span class="bot-badge ${botBadgeClass}" style="font-size: 16px; padding: 4px 12px;">${botDisplayName}</span></h4>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                                <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Всего сделок</div>
                                    <div style="font-size: 20px; font-weight: bold; color: #667eea;">${botStats.total_trades || 0}</div>
                                </div>
                                <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Прибыльных</div>
                                    <div style="font-size: 20px; font-weight: bold; color: #10b981;">${botStats.winning_trades || 0}</div>
                                </div>
                                <div style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Убыточных</div>
                                    <div style="font-size: 20px; font-weight: bold; color: #ef4444;">${botStats.losing_trades || 0}</div>
                                </div>
                                <div style="background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Винрейт</div>
                                    <div style="font-size: 20px; font-weight: bold; color: #f59e0b;">${winRate.toFixed(1)}%</div>
                                </div>
                                <div style="background: linear-gradient(135deg, ${totalPnl >= 0 ? '#f0fdf4 0%, #dcfce7 100%' : '#fef2f2 0%, #fee2e2 100%'}); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Общий P&L</div>
                                    <div style="font-size: 20px; font-weight: bold; color: ${totalPnl >= 0 ? '#10b981' : '#ef4444'};">${totalPnl >= 0 ? '+' : ''}${formatNumber(Math.abs(totalPnl), 2)} USDT</div>
                                </div>
                                <div style="background: linear-gradient(135deg, ${avgPnl >= 0 ? '#f0fdf4 0%, #dcfce7 100%' : '#fef2f2 0%, #fee2e2 100%'}); padding: 12px; border-radius: 8px;">
                                    <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Средний P&L</div>
                                    <div style="font-size: 20px; font-weight: bold; color: ${avgPnl >= 0 ? '#10b981' : '#ef4444'};">${avgPnl >= 0 ? '+' : ''}${formatNumber(Math.abs(avgPnl), 2)} USDT</div>
                                </div>
                            </div>
                        `;
                        botsContainer.appendChild(card);
                    });
                }
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Загрузка позиций (с автообновлением каждые 5 секунд)
let positionsUpdateInterval = null;

async function loadPositions() {
    try {
        const response = await fetch('api.php?action=positions&_t=' + Date.now()); // Добавляем timestamp для избежания кэша
        const data = await response.json();
        
        // Отладочная информация
        if (data.positions && data.positions.length > 0) {
            console.log('Загружено позиций:', data.positions.length);
            const positionsWithTrades = data.positions.filter(p => p.open_trades && p.open_trades.length > 0);
            if (positionsWithTrades.length > 0) {
                console.log('Позиции с открытыми сделками:', positionsWithTrades.map(p => ({
                    symbol: p.symbol,
                    trades: p.open_trades
                })));
            }
        }
        
        if (data.positions) {
            const grid = document.getElementById('market-grid');
            grid.innerHTML = '';
            
            // Убираем дубликаты по символу (берем только последний)
            const uniquePositions = {};
            data.positions.forEach(position => {
                if (!uniquePositions[position.symbol] || 
                    new Date(position.timestamp) > new Date(uniquePositions[position.symbol].timestamp)) {
                    uniquePositions[position.symbol] = position;
                }
            });
            
            const sortedPositions = Object.values(uniquePositions).sort((a, b) => {
                // Сортируем по объему торгов (от большего к меньшему)
                return b.volume_24h - a.volume_24h;
            });
            
            sortedPositions.forEach(position => {
                const card = document.createElement('div');
                card.className = 'market-card';
                
                // Определяем цвет тренда
                const change24h = position.change_24h || 0;
                const trendClass = change24h > 0 ? 'trend-up' : change24h < 0 ? 'trend-down' : 'trend-neutral';
                const trendIcon = change24h > 0 ? '📈' : change24h < 0 ? '📉' : '➡️';
                const changeSign = change24h >= 0 ? '+' : '';
                
                // Определяем статус RSI
                let rsiStatus = '';
                let rsiClass = '';
                if (position.rsi) {
                    if (position.rsi > 70) {
                        rsiStatus = 'Перекуплен';
                        rsiClass = 'rsi-overbought';
                    } else if (position.rsi < 30) {
                        rsiStatus = 'Перепродан';
                        rsiClass = 'rsi-oversold';
                    } else {
                        rsiStatus = 'Нейтрально';
                        rsiClass = 'rsi-neutral';
                    }
                }
                
                // Индикатор реального времени
                const realtimeBadge = position.realtime ? '<span class="realtime-badge">LIVE</span>' : '';
                
                // Индикатор открытых сделок
                let tradesBadge = '';
                if (position.open_trades && position.open_trades.length > 0) {
                    const trades = position.open_trades;
                    const mainTrades = trades.filter(t => t.bot_name === 'main' || t.bot_name === 'Main');
                    const iliyaTrades = trades.filter(t => t.bot_name === 'iliya' || t.bot_name === 'Iliya');
                    const longTrades = trades.filter(t => {
                        const side = (t.side || '').toLowerCase();
                        return side === 'long' || side === 'buy';
                    });
                    const shortTrades = trades.filter(t => {
                        const side = (t.side || '').toLowerCase();
                        return side === 'short' || side === 'sell';
                    });
                    
                    let tradeIcons = [];
                    
                    // Иконки ботов
                    if (mainTrades.length > 0) {
                        const mainLong = mainTrades.filter(t => {
                            const side = (t.side || '').toLowerCase();
                            return side === 'long' || side === 'buy';
                        }).length;
                        const mainShort = mainTrades.filter(t => {
                            const side = (t.side || '').toLowerCase();
                            return side === 'short' || side === 'sell';
                        }).length;
                        const mainInfo = [];
                        if (mainLong > 0) mainInfo.push(`${mainLong} ЛОНГ`);
                        if (mainShort > 0) mainInfo.push(`${mainShort} ШОРТ`);
                        const title = `Main: ${mainTrades.length} сделок (${mainInfo.join(', ')})`;
                        tradeIcons.push(`<span class="trade-badge trade-main highlighted" title="${title}">🤖 Main</span>`);
                    }
                    if (iliyaTrades.length > 0) {
                        const iliyaLong = iliyaTrades.filter(t => {
                            const side = (t.side || '').toLowerCase();
                            return side === 'long' || side === 'buy';
                        }).length;
                        const iliyaShort = iliyaTrades.filter(t => {
                            const side = (t.side || '').toLowerCase();
                            return side === 'short' || side === 'sell';
                        }).length;
                        const iliyaInfo = [];
                        if (iliyaLong > 0) iliyaInfo.push(`${iliyaLong} ЛОНГ`);
                        if (iliyaShort > 0) iliyaInfo.push(`${iliyaShort} ШОРТ`);
                        const title = `Iliya: ${iliyaTrades.length} сделок (${iliyaInfo.join(', ')})`;
                        tradeIcons.push(`<span class="trade-badge trade-iliya highlighted" title="${title}">👤 Iliya</span>`);
                    }
                    
                    // Иконки направления (только если есть сделки)
                    if (longTrades.length > 0) {
                        tradeIcons.push(`<span class="trade-badge trade-long" title="ЛОНГ: ${longTrades.length}">📈</span>`);
                    }
                    if (shortTrades.length > 0) {
                        tradeIcons.push(`<span class="trade-badge trade-short" title="ШОРТ: ${shortTrades.length}">📉</span>`);
                    }
                    
                    tradesBadge = tradeIcons.length > 0 ? '<div class="trade-icons-container">' + tradeIcons.join('') + '</div>' : '';
                    
                    // Отладочная информация
                    console.log(`Символ ${position.symbol}:`, {
                        total: trades.length,
                        main: mainTrades.length,
                        iliya: iliyaTrades.length,
                        long: longTrades.length,
                        short: shortTrades.length,
                        trades: trades
                    });
                }
                
                // Определяем формат цены
                let priceFormat = 2;
                if (position.symbol.includes('BTC') || position.symbol.includes('ETH')) {
                    priceFormat = position.price > 1000 ? 2 : 4;
                } else if (position.price < 1) {
                    priceFormat = 6;
                } else if (position.price < 10) {
                    priceFormat = 4;
                }
                
                card.innerHTML = `
                    <div class="market-card-header">
                        <div class="symbol">
                            ${position.symbol.replace('USDT', '')} ${realtimeBadge}
                            ${tradesBadge}
                        </div>
                        <div class="trend ${trendClass}">
                            ${trendIcon} ${changeSign}${formatNumber(change24h, 2)}%
                        </div>
                    </div>
                    <div class="price">$${formatNumber(position.price, priceFormat)}</div>
                    <div class="market-stats">
                        <div class="stat-row">
                            <span class="stat-label">Объем 24ч:</span>
                            <span class="stat-value">${formatVolume(position.volume_24h)}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Волатильность:</span>
                            <span class="stat-value">${formatNumber(position.volatility, 2)}%</span>
                        </div>
                        ${position.rsi ? `
                        <div class="stat-row">
                            <span class="stat-label">RSI:</span>
                            <span class="stat-value ${rsiClass}">${formatNumber(position.rsi, 1)} <small>(${rsiStatus})</small></span>
                        </div>
                        ` : ''}
                        ${position.macd !== null ? `
                        <div class="stat-row">
                            <span class="stat-label">MACD:</span>
                            <span class="stat-value ${position.macd > 0 ? 'positive' : 'negative'}">${formatNumber(position.macd, 4)}</span>
                        </div>
                        ` : ''}
                    </div>
                    <div class="market-footer">
                        <small>Обновлено: ${formatTimeShort(position.timestamp)}</small>
                    </div>
                `;
                grid.appendChild(card);
            });
        }
    } catch (error) {
        console.error('Ошибка загрузки позиций:', error);
    }
}

// Пагинация для сделок
let tradesCurrentPage = 1;
const tradesPerPage = 15;

// Загрузка сделок
async function loadTrades(botFilter = 'all', page = 1) {
    try {
        const url = botFilter === 'all' 
            ? `api.php?action=trades&limit=${tradesPerPage}&offset=${(page - 1) * tradesPerPage}`
            : `api.php?action=trades&limit=${tradesPerPage}&offset=${(page - 1) * tradesPerPage}&bot=${botFilter}`;
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.trades) {
            const tbody = document.getElementById('trades-tbody');
            tbody.innerHTML = '';
            
            if (data.trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="loading">Нет данных</td></tr>';
                return;
            }
            
            // Подсчитываем общую статистику
            let totalPnl = 0;
            let closedTrades = 0;
            let winningTrades = 0;
            let losingTrades = 0;
            
            data.trades.forEach(trade => {
                if (trade.pnl !== null && trade.pnl !== undefined) {
                    const pnl = parseFloat(trade.pnl);
                    totalPnl += pnl;
                    closedTrades++;
                    if (pnl > 0) winningTrades++;
                    if (pnl < 0) losingTrades++;
                }
            });
            
            // Добавляем сводку перед таблицей, если есть данные
            const summaryElement = document.getElementById('trades-summary');
            if (summaryElement) {
                if (closedTrades > 0) {
                    const winRate = ((winningTrades / closedTrades) * 100).toFixed(1);
                    const totalPnlClass = totalPnl >= 0 ? 'positive' : 'negative';
                    const totalPnlSign = totalPnl >= 0 ? '+' : '';
                    summaryElement.innerHTML = `
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                            <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #667eea;">
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px;">Общий P&L</div>
                                <div style="font-size: 24px; font-weight: bold; color: #667eea;">${totalPnlSign}${formatNumber(Math.abs(totalPnl), 2)} USDT</div>
                            </div>
                            <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #10b981;">
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px;">Закрытых сделок</div>
                                <div style="font-size: 24px; font-weight: bold; color: #10b981;">${closedTrades}</div>
                            </div>
                            <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #10b981;">
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px;">Прибыльных</div>
                                <div style="font-size: 24px; font-weight: bold; color: #10b981;">${winningTrades}</div>
                            </div>
                            <div style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #ef4444;">
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px;">Убыточных</div>
                                <div style="font-size: 24px; font-weight: bold; color: #ef4444;">${losingTrades}</div>
                            </div>
                            <div style="background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #fbbf24;">
                                <div style="font-size: 12px; color: #6b7280; margin-bottom: 5px;">Винрейт</div>
                                <div style="font-size: 24px; font-weight: bold; color: #f59e0b;">${winRate}%</div>
                            </div>
                        </div>
                    `;
                } else {
                    summaryElement.innerHTML = '<div style="padding: 10px; background: #f3f4f6; border-radius: 6px; color: #6b7280; text-align: center;">Нет закрытых сделок с данными о P&L</div>';
                }
            }
            
            data.trades.forEach(trade => {
                const row = document.createElement('tr');
                const pnlClass = trade.pnl && trade.pnl >= 0 ? 'positive' : trade.pnl && trade.pnl < 0 ? 'negative' : '';
                const pnlSign = trade.pnl && trade.pnl >= 0 ? '+' : '';
                const botBadge = trade.bot_name === 'iliya' ? '<span class="bot-badge bot-iliya">Iliya</span>' : '<span class="bot-badge bot-main">Main</span>';
                const statusBadge = trade.status === 'open' ? '<span class="status-badge status-open">Открыта</span>' : '<span class="status-badge status-closed">Закрыта</span>';
                
                // Форматирование цены в зависимости от символа
                let entryPriceFormat = 2;
                let exitPriceFormat = 2;
                if (trade.symbol.includes('BTC') || trade.symbol.includes('ETH')) {
                    entryPriceFormat = trade.entry_price > 1000 ? 2 : 4;
                    exitPriceFormat = trade.exit_price && trade.exit_price > 1000 ? 2 : 4;
                } else if (trade.entry_price < 1) {
                    entryPriceFormat = 6;
                    exitPriceFormat = 6;
                } else if (trade.entry_price < 10) {
                    entryPriceFormat = 4;
                    exitPriceFormat = 4;
                }
                
                // Форматируем время входа и выхода
                const entryTime = formatTime(trade.timestamp);
                const exitTime = trade.exit_time ? formatTime(trade.exit_time) : '-';
                
                // Форматируем направление сделки
                const sideDisplay = trade.side === 'Long' || trade.side === 'Buy' ? 
                    '<span style="color: #10b981; font-weight: bold;">📈 ЛОНГ</span>' : 
                    '<span style="color: #ef4444; font-weight: bold;">📉 ШОРТ</span>';
                
                // Правильно определяем статус: открыта если status='open' И нет exit_price
                const isOpen = trade.status === 'open' && !trade.exit_price;
                
                // Форматируем P&L более наглядно
                let pnlDisplay = '';
                if (isOpen) {
                    pnlDisplay = '<span style="color: #fbbf24; font-weight: 600;">⏳ Открыта</span>';
                } else if (trade.pnl !== null && trade.pnl !== undefined) {
                    const pnlValue = parseFloat(trade.pnl);
                    const pnlPercent = trade.pnl_percent ? parseFloat(trade.pnl_percent) : null;
                    const pnlBgClass = pnlValue >= 0 ? 'positive' : 'negative';
                    
                    pnlDisplay = `
                        <div class="pnl-display ${pnlBgClass}" style="padding: 8px; border-radius: 6px; margin-bottom: 4px;">
                            <div style="font-size: 18px; font-weight: bold;">
                                ${pnlSign}${formatNumber(Math.abs(pnlValue), 2)} USDT
                            </div>
                            ${pnlPercent !== null ? `
                                <div style="font-size: 13px; margin-top: 2px;">
                                    ${pnlSign}${formatNumber(Math.abs(pnlPercent), 2)}%
                                </div>
                            ` : ''}
                        </div>
                    `;
                } else {
                    pnlDisplay = '<span style="color: #9ca3af;">Нет данных</span>';
                }
                
                row.innerHTML = `
                    <td>
                        <div style="font-weight: 600; font-size: 14px;">${entryTime}</div>
                        ${exitTime !== '-' ? `<div style="font-size: 11px; color: #6b7280; margin-top: 4px;">Выход: ${exitTime}</div>` : ''}
                    </td>
                    <td>
                        <div style="font-weight: bold; font-size: 16px; margin-bottom: 4px;">${trade.symbol.replace('USDT', '')}</div>
                        <div style="margin-bottom: 4px;">${botBadge}</div>
                        ${statusBadge}
                    </td>
                    <td style="font-size: 15px;">${sideDisplay}</td>
                    <td style="font-weight: 700; color: #667eea; font-size: 15px;">
                        $${formatNumber(trade.entry_price, entryPriceFormat)}
                    </td>
                    <td style="font-weight: 700; color: ${trade.exit_price ? '#667eea' : '#9ca3af'}; font-size: 15px;">
                        ${trade.exit_price ? '$' + formatNumber(trade.exit_price, exitPriceFormat) : (isOpen ? '<span style="color: #fbbf24; font-size: 13px;">⏳ Открыта</span>' : '<span style="color: #9ca3af; font-size: 13px;">—</span>')}
                    </td>
                    <td>
                        <div style="font-weight: 600;">${formatNumber(trade.quantity, 6)}</div>
                        ${trade.leverage ? `<div style="font-size: 11px; color: #6b7280; margin-top: 2px;">${trade.leverage}x</div>` : ''}
                    </td>
                    <td class="${pnlClass}" style="font-size: 15px; text-align: center;">
                        ${pnlDisplay}
                    </td>
                `;
                tbody.appendChild(row);
            });
            
            // Добавляем пагинацию
            const totalPages = Math.ceil((data.total || data.trades.length) / tradesPerPage);
            updateTradesPagination(page, totalPages, botFilter);
        }
    } catch (error) {
        console.error('Ошибка загрузки сделок:', error);
    }
}

// Обновление пагинации для сделок
function updateTradesPagination(currentPage, totalPages, botFilter) {
    let paginationContainer = document.getElementById('trades-pagination');
    if (!paginationContainer) {
        paginationContainer = document.createElement('div');
        paginationContainer.id = 'trades-pagination';
        paginationContainer.className = 'pagination';
        document.getElementById('trades-table').parentElement.appendChild(paginationContainer);
    }
    
    if (totalPages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    if (currentPage > 1) {
        html += `<button onclick="tradesCurrentPage = ${currentPage - 1}; loadTrades('${botFilter}', tradesCurrentPage);" class="pagination-btn">← Назад</button>`;
    }
    html += `<span class="pagination-info">Страница ${currentPage} из ${totalPages}</span>`;
    if (currentPage < totalPages) {
        html += `<button onclick="tradesCurrentPage = ${currentPage + 1}; loadTrades('${botFilter}', tradesCurrentPage);" class="pagination-btn">Вперед →</button>`;
    }
    html += '</div>';
    paginationContainer.innerHTML = html;
}

// Пагинация для AI ответов
let aiCurrentPage = 1;
const aiPerPage = 15;

// Загрузка AI ответов (в формате чата)
async function loadAIResponses(page = 1) {
    try {
        const response = await fetch(`api.php?action=ai_responses&limit=${aiPerPage}&offset=${(page - 1) * aiPerPage}`);
        const data = await response.json();
        
        const container = document.getElementById('ai-chat-container');
        container.innerHTML = '';
        
        if (!data.responses || data.responses.length === 0) {
            container.innerHTML = '<div class="ai-chat-empty">Нет данных</div>';
            updateAIPagination(page, 1);
            return;
        }
        
        data.responses.forEach(item => {
            const card = document.createElement('div');
            card.className = 'ai-chat-card';
            
            const header = document.createElement('div');
            header.className = 'ai-chat-header';
            header.innerHTML = `
                <div class="ai-chat-header-left">
                    <span class="ai-chat-time">${formatTime(item.timestamp)}</span>
                    <span class="ai-type-badge">${formatAIRequestType(item.request_type)}</span>
                    ${formatAIConfidence(item.confidence)}
                </div>
                <div class="ai-chat-header-right">
                    <span class="ai-symbol-chip">${formatAISymbols(item) || '—'}</span>
                    ${item.side ? `<span class="ai-side-badge">${item.side}</span>` : ''}
                </div>
            `;
            card.appendChild(header);
            
            const details = [];
            if (item.entry_price) details.push(`Вход: $${formatNumber(item.entry_price)}`);
            if (item.stop_loss) details.push(`SL: $${formatNumber(item.stop_loss)}`);
            if (item.take_profit) details.push(`TP: $${formatNumber(item.take_profit)}`);
            if (details.length) {
                const meta = document.createElement('div');
                meta.className = 'ai-chat-meta';
                meta.textContent = details.join(' • ');
                card.appendChild(meta);
            }
            
            (item.chat_blocks || []).forEach(block => {
                card.appendChild(createAIChatBlock(block));
            });
            
            container.appendChild(card);
        });
        
        const totalPages = Math.ceil((data.total || data.responses.length) / aiPerPage);
        updateAIPagination(page, totalPages);
    } catch (error) {
        console.error('Ошибка загрузки AI ответов:', error);
    }
}

function createAIChatBlock(block) {
    const blockEl = document.createElement('div');
    blockEl.className = `ai-chat-block ${block.role === 'user' ? 'ai-chat-user' : 'ai-chat-bot'} collapsed`;
    
    const header = document.createElement('button');
    header.type = 'button';
    header.className = 'ai-chat-block-toggle';
    header.innerHTML = `
        <span>${block.title || (block.role === 'user' ? 'USER' : 'AI')}</span>
        <span class="ai-chat-toggle-icon">+</span>
    `;
    blockEl.appendChild(header);
    
    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'ai-chat-block-content-wrapper';
    
    const content = document.createElement('pre');
    content.className = 'ai-chat-block-content';
    content.textContent = block.content || '—';
    contentWrapper.appendChild(content);
    
    blockEl.appendChild(contentWrapper);
    
    header.addEventListener('click', () => {
        const isCollapsed = blockEl.classList.toggle('collapsed');
        header.querySelector('.ai-chat-toggle-icon').textContent = isCollapsed ? '+' : '−';
        if (!isCollapsed) {
            const fullHeight = content.scrollHeight;
            contentWrapper.style.maxHeight = `${fullHeight + 30}px`;
        } else {
            contentWrapper.style.maxHeight = '0px';
        }
    });
    
    return blockEl;
}

// Обновление пагинации для AI
function updateAIPagination(currentPage, totalPages) {
    const paginationContainer = document.getElementById('ai-pagination');
    
    if (totalPages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    if (currentPage > 1) {
        html += `<button onclick="aiCurrentPage = ${currentPage - 1}; loadAIResponses(aiCurrentPage);" class="pagination-btn">← Назад</button>`;
    }
    html += `<span class="pagination-info">Страница ${currentPage} из ${totalPages}</span>`;
    if (currentPage < totalPages) {
        html += `<button onclick="aiCurrentPage = ${currentPage + 1}; loadAIResponses(aiCurrentPage);" class="pagination-btn">Вперед →</button>`;
    }
    html += '</div>';
    paginationContainer.innerHTML = html;
}

// Пагинация для ошибок
let errorsCurrentPage = 1;
const errorsPerPage = 15;

// Загрузка ошибок
async function loadErrors(page = 1) {
    try {
        const response = await fetch(`api.php?action=errors&limit=${errorsPerPage}&offset=${(page - 1) * errorsPerPage}`);
        const data = await response.json();
        
        if (data.errors) {
            const tbody = document.getElementById('errors-tbody');
            tbody.innerHTML = '';
            
            if (data.errors.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="loading">Нет ошибок</td></tr>';
                return;
            }
            
            data.errors.forEach(error => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${formatTime(error.timestamp)}</td>
                    <td>${error.api_method}</td>
                    <td>${error.symbol || '-'}</td>
                    <td>${error.error_code || '-'}</td>
                    <td>${error.error_message || '-'}</td>
                `;
                tbody.appendChild(row);
            });
            
            // Добавляем пагинацию
            const totalPages = Math.ceil((data.total || data.errors.length) / errorsPerPage);
            updateErrorsPagination(page, totalPages);
        }
    } catch (error) {
        console.error('Ошибка загрузки ошибок:', error);
    }
}

// Обновление пагинации для ошибок
function updateErrorsPagination(currentPage, totalPages) {
    let paginationContainer = document.getElementById('errors-pagination');
    if (!paginationContainer) {
        paginationContainer = document.createElement('div');
        paginationContainer.id = 'errors-pagination';
        paginationContainer.className = 'pagination';
        document.getElementById('errors-table').parentElement.appendChild(paginationContainer);
    }
    
    if (totalPages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    if (currentPage > 1) {
        html += `<button onclick="errorsCurrentPage = ${currentPage - 1}; loadErrors(errorsCurrentPage);" class="pagination-btn">← Назад</button>`;
    }
    html += `<span class="pagination-info">Страница ${currentPage} из ${totalPages}</span>`;
    if (currentPage < totalPages) {
        html += `<button onclick="errorsCurrentPage = ${currentPage + 1}; loadErrors(errorsCurrentPage);" class="pagination-btn">Вперед →</button>`;
    }
    html += '</div>';
    paginationContainer.innerHTML = html;
}


// Вспомогательные функции
function formatNumber(num, decimals = 2) {
    const parts = Number(num).toFixed(decimals).split('.');
    // Добавляем пробелы только в целой части числа
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return parts.join('.');
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleString('ru-RU');
}

function formatTimeShort(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function formatVolume(volume) {
    if (volume >= 1000000000) {
        return (volume / 1000000000).toFixed(2) + 'B';
    } else if (volume >= 1000000) {
        return (volume / 1000000).toFixed(2) + 'M';
    } else if (volume >= 1000) {
        return (volume / 1000).toFixed(2) + 'K';
    }
    return formatNumber(volume, 0);
}

function formatAIRequestType(type) {
    const map = {
        'market_analysis': 'Анализ рынка',
        'trade_selection': 'Выбор монеты',
        'trade_plan': 'План сделки'
    };
    return map[type] || (type ? type : 'Запрос AI');
}

function formatAISymbols(response) {
    if (response.symbols && response.symbols.length > 0) {
        return response.symbols.join(', ');
    }
    if (response.symbol) {
        return response.symbol;
    }
    return '';
}

function formatAIConfidence(confidence) {
    if (confidence === null || confidence === undefined || Number.isNaN(Number(confidence))) {
        return '';
    }
    return `<span class="ai-confidence-badge">Уверенность: ${formatNumber(confidence, 1)}%</span>`;
}

