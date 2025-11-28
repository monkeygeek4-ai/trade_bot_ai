<?php
require_once 'config.php';
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
    <title>Мониторинг торгового бота</title>
    <link rel="icon" type="image/svg+xml" href="favicon.svg">
    <link rel="alternate icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%23667eea'/><text x='50' y='70' font-size='60' fill='white' text-anchor='middle'>📈</text></svg>">
    <link rel="stylesheet" href="style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Мониторинг торгового бота</h1>
            <div class="last-update">Последнее обновление: <span id="last-update">загрузка...</span></div>
        </header>

        <!-- Статистика за 24 часа -->
        <section class="stats-section">
            <h2>📊 Статистика за 24 часа</h2>
            
            <!-- Общая статистика -->
            <h3 style="margin-top: 0; margin-bottom: 15px; font-size: 18px; color: #374151;">Общая статистика</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Всего сделок</div>
                    <div class="stat-value" id="stat-total-trades">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Прибыльных</div>
                    <div class="stat-value positive" id="stat-winning">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Убыточных</div>
                    <div class="stat-value negative" id="stat-losing">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Винрейт</div>
                    <div class="stat-value" id="stat-winrate">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Общий P&L</div>
                    <div class="stat-value" id="stat-total-pnl">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Средний P&L</div>
                    <div class="stat-value" id="stat-avg-pnl">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">AI ответов</div>
                    <div class="stat-value" id="stat-ai-responses">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Ошибок</div>
                    <div class="stat-value" id="stat-errors">-</div>
                </div>
            </div>
            
            <!-- Статистика по ботам -->
            <h3 style="margin-top: 30px; margin-bottom: 15px; font-size: 18px; color: #374151;">Статистика по ботам</h3>
            <div id="bots-stats-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">
                <!-- Заполняется через JavaScript -->
            </div>
        </section>

        <!-- Рыночные данные -->
        <section class="market-section">
            <h2>📈 Рыночные данные</h2>
            <div class="market-grid" id="market-grid">
                <!-- Заполняется через JavaScript -->
            </div>
        </section>

        <!-- Последние сделки -->
        <section class="trades-section">
            <h2>💼 Последние сделки</h2>
            <div style="margin-bottom: 15px; padding: 10px; background: #fef3c7; border-left: 4px solid #fbbf24; border-radius: 4px; font-size: 13px; color: #78350f;">
                💡 <strong>Примечание:</strong> Для старых сделок данные о выходе и P&L могут отсутствовать. Новые сделки обновляются автоматически при закрытии.
            </div>
            <div id="trades-summary"></div>
            <div class="bot-filters">
                <button class="bot-filter active" data-bot="all">Все боты</button>
                <button class="bot-filter" data-bot="main">Main</button>
                <button class="bot-filter" data-bot="iliya">Iliya</button>
            </div>
            <div class="table-container">
                <table id="trades-table">
                    <thead>
                        <tr>
                            <th>Время входа</th>
                            <th>Символ / Бот</th>
                            <th>Направление</th>
                            <th>💰 Цена входа</th>
                            <th>💰 Цена выхода</th>
                            <th>Размер / Плечо</th>
                            <th>💵 P&L (USDT / %)</th>
                        </tr>
                    </thead>
                    <tbody id="trades-tbody">
                        <tr><td colspan="7" class="loading">Загрузка...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Последние AI рекомендации -->
        <section class="ai-section">
            <h2>🤖 Последние AI рекомендации</h2>
            <div id="ai-chat-container" class="ai-chat-container">
                <div class="loading">Загрузка...</div>
            </div>
            <div id="ai-pagination" class="pagination"></div>
        </section>

        <!-- Последние ошибки -->
        <section class="errors-section">
            <h2>⚠️ Последние ошибки</h2>
            <div class="table-container">
                <table id="errors-table">
                    <thead>
                        <tr>
                            <th>Время</th>
                            <th>Метод</th>
                            <th>Символ</th>
                            <th>Код</th>
                            <th>Сообщение</th>
                        </tr>
                    </thead>
                    <tbody id="errors-tbody">
                        <tr><td colspan="5" class="loading">Загрузка...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
    </div>

    <script src="app.js"></script>
</body>
</html>

