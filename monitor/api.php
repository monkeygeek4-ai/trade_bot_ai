<?php
/**
 * API для получения данных мониторинга
 */

// Включаем отображение ошибок для отладки (в продакшене убрать)
error_reporting(E_ALL);
ini_set('display_errors', 0);
ini_set('log_errors', 1);

require_once 'config.php';

// Обработка ошибок
set_error_handler(function($errno, $errstr, $errfile, $errline) {
    error_log("PHP Error [$errno]: $errstr in $errfile:$errline");
    if ($errno === E_ERROR || $errno === E_PARSE || $errno === E_CORE_ERROR) {
        jsonResponse(['error' => 'Внутренняя ошибка сервера', 'message' => $errstr], 500);
    }
    return false;
});

register_shutdown_function(function() {
    $error = error_get_last();
    if ($error && in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR])) {
        jsonResponse(['error' => 'Внутренняя ошибка сервера', 'message' => $error['message']], 500);
    }
});

try {
    $action = $_GET['action'] ?? '';
    
    if (empty($action)) {
        jsonResponse(['error' => 'Не указано действие'], 400);
    }
    
    switch ($action) {
        case 'positions':
            getPositions();
            break;
        case 'stats':
            getStats();
            break;
        case 'trades':
            getRecentTrades();
            break;
        case 'ai_responses':
            getAIResponses();
            break;
        case 'errors':
            getRecentErrors();
            break;
        case 'market_data':
            getMarketData();
            break;
        default:
            jsonResponse(['error' => 'Неизвестное действие'], 400);
    }
} catch (Exception $e) {
    error_log("Exception in api.php: " . $e->getMessage());
    jsonResponse(['error' => 'Внутренняя ошибка сервера', 'message' => $e->getMessage()], 500);
}

// Кэш для реальных цен (5 секунд)
$realtime_cache = [];
$realtime_cache_time = [];

function getRealtimePrice($symbol) {
    global $realtime_cache, $realtime_cache_time;
    
    $cache_key = $symbol;
    $cache_ttl = 5; // 5 секунд
    
    // Проверяем кэш
    if (isset($realtime_cache[$cache_key]) && 
        isset($realtime_cache_time[$cache_key]) &&
        (time() - $realtime_cache_time[$cache_key]) < $cache_ttl) {
        return $realtime_cache[$cache_key];
    }
    
    // Получаем данные из Bybit публичного API
    try {
        $url = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=" . urlencode($symbol);
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 10); // Увеличиваем таймаут до 10 секунд
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 5);
        curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
        $response = curl_exec($ch);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($http_code === 200 && $response) {
            $data = json_decode($response, true);
            if ($data && $data['retCode'] == 0 && isset($data['result']['list'][0])) {
                $ticker = $data['result']['list'][0];
                $result = [
                    'price' => floatval($ticker['lastPrice']),
                    'change_24h' => floatval($ticker['price24hPcnt']) * 100,
                    'volume_24h' => floatval($ticker['volume24h']),
                    'high_24h' => floatval($ticker['highPrice24h'] ?? 0),
                    'low_24h' => floatval($ticker['lowPrice24h'] ?? 0),
                    'timestamp' => date('Y-m-d H:i:s')
                ];
                
                // Сохраняем в кэш
                $realtime_cache[$cache_key] = $result;
                $realtime_cache_time[$cache_key] = time();
                
                return $result;
            }
        }
    } catch (Exception $e) {
        error_log("Ошибка получения реальной цены для $symbol: " . $e->getMessage());
    }
    
    return null;
}

function getPositions() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'positions' => []], 200);
        }
    
    // Список символов для мониторинга (только доступные на Bybit для фьючерсов)
    // SHIBUSDT и PEPEUSDT убраны - недоступны для фьючерсов
    $symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'POLUSDT', 'TONUSDT', 'TRXUSDT', 'LTCUSDT', 'NEARUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'SEIUSDT', 'SUIUSDT'];
    
    // Получаем открытые сделки из БД
    // Проверяем наличие колонки bot_name
    $check_column = $conn->query("SHOW COLUMNS FROM trades_history LIKE 'bot_name'");
    $has_bot_name = $check_column && $check_column->rowCount() > 0;
    
    // Получаем открытые сделки из БД для ОБОИХ ботов
    // Открытые = те, у которых exit_time IS NULL И status = 'open'
    // И только недавние (последние 7 дней), чтобы исключить старые "зависшие" записи
    $open_trades_query = $has_bot_name 
        ? "SELECT symbol, bot_name, side, entry_price, quantity, leverage, status, entry_time
           FROM trades_history
           WHERE exit_time IS NULL 
           AND status = 'open'
           AND entry_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
           ORDER BY entry_time DESC"
        : "SELECT symbol, 'main' as bot_name, side, entry_price, quantity, leverage, status, entry_time
           FROM trades_history
           WHERE exit_time IS NULL 
           AND status = 'open'
           AND entry_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
           ORDER BY entry_time DESC";
    
    $open_trades_stmt = $conn->query($open_trades_query);
    $open_trades = [];
    $total_trades_found = 0;
    
    if ($open_trades_stmt) {
        while ($row = $open_trades_stmt->fetch()) {
            $symbol = $row['symbol'];
            $bot_name = $row['bot_name'] ?? 'main';
            $side = $row['side'] ?? null;
            
            // Пропускаем сделки без направления
            if (!$side) {
                continue;
            }
            
            if (!isset($open_trades[$symbol])) {
                $open_trades[$symbol] = [];
            }
            
            $open_trades[$symbol][] = [
                'bot_name' => $bot_name,
                'side' => $side,
                'entry_price' => floatval($row['entry_price'] ?? 0),
                'quantity' => floatval($row['quantity'] ?? 0),
                'leverage' => intval($row['leverage'] ?? 1)
            ];
            $total_trades_found++;
        }
    }
    
    // Отладочная информация
    error_log("=== ОТКРЫТЫЕ СДЕЛКИ ===");
    error_log("Всего найдено открытых сделок: " . $total_trades_found);
    error_log("Символов с открытыми сделками: " . count($open_trades));
    
    if (count($open_trades) > 0) {
        foreach ($open_trades as $symbol => $trades) {
            $main_count = 0;
            $iliya_count = 0;
            foreach ($trades as $trade) {
                if ($trade['bot_name'] === 'main') $main_count++;
                if ($trade['bot_name'] === 'iliya') $iliya_count++;
            }
            error_log("  $symbol: " . count($trades) . " сделок (Main: $main_count, Iliya: $iliya_count)");
            foreach ($trades as $trade) {
                error_log("    - {$trade['bot_name']}: {$trade['side']} @ {$trade['entry_price']}");
            }
        }
    } else {
        error_log("  Нет открытых сделок!");
    }
    
    // Получаем реальные цены напрямую из Bybit API
    $realtime_prices = [];
    foreach ($symbols as $symbol) {
        $realtime = getRealtimePrice($symbol);
        if ($realtime) {
            $realtime_prices[$symbol] = $realtime;
        }
    }
    
    // Получаем последние данные из market_history для каждой монеты (для индикаторов)
    // Используем подзапрос с MAX(id) для гарантии уникальности
    // Расширяем временной диапазон до 24 часов для поиска последних данных
    $query = "
        SELECT 
            mh.symbol,
            mh.price as current_price,
            mh.volume_24h,
            mh.volatility,
            mh.rsi,
            mh.atr,
            mh.macd,
            mh.timestamp,
            old.price as price_24h_ago,
            CASE 
                WHEN old.price > 0 THEN ((mh.price - old.price) / old.price * 100)
                ELSE 0
            END as change_24h
        FROM market_history mh
        INNER JOIN (
            SELECT symbol, MAX(id) as max_id
            FROM market_history
            WHERE symbol IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'POLUSDT', 'TONUSDT', 'TRXUSDT', 'LTCUSDT', 'NEARUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'SEIUSDT', 'SUIUSDT')
            AND timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY symbol
        ) latest ON mh.id = latest.max_id
        LEFT JOIN (
            SELECT mh2.symbol, mh2.price
            FROM market_history mh2
            INNER JOIN (
                SELECT symbol, MAX(id) as max_id
                FROM market_history
                WHERE timestamp <= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                AND timestamp >= DATE_SUB(NOW(), INTERVAL 48 HOUR)
                AND symbol IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'POLUSDT')
                GROUP BY symbol
            ) old_latest ON mh2.id = old_latest.max_id
        ) old ON mh.symbol = old.symbol
        WHERE mh.symbol IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'POLUSDT')
        ORDER BY mh.volume_24h DESC
    ";
    
    $stmt = $conn->query($query);
    $positions = [];
    
    if ($stmt) {
        while ($row = $stmt->fetch()) {
            $symbol = $row['symbol'];
            
            // Используем реальную цену из Bybit API, если доступна
            $realtime = $realtime_prices[$symbol] ?? null;
            
            $positions[] = [
                'symbol' => $symbol,
                'price' => $realtime ? $realtime['price'] : floatval($row['current_price']),
                'price_24h_ago' => $row['price_24h_ago'] ? floatval($row['price_24h_ago']) : null,
                'change_24h' => $realtime ? $realtime['change_24h'] : floatval($row['change_24h'] ?? 0),
                'volume_24h' => $realtime ? $realtime['volume_24h'] : floatval($row['volume_24h']),
                'volatility' => floatval($row['volatility']),
                'rsi' => $row['rsi'] ? floatval($row['rsi']) : null,
                'atr' => $row['atr'] ? floatval($row['atr']) : null,
                'macd' => $row['macd'] ? floatval($row['macd']) : null,
                'timestamp' => $realtime ? $realtime['timestamp'] : $row['timestamp'],
                'realtime' => $realtime !== null, // Флаг, что данные реальные
                'open_trades' => $open_trades[$symbol] ?? [] // Открытые сделки по этому символу
            ];
        }
    }
    
    // Если нет данных в БД, используем только реальные цены
    if (empty($positions)) {
        foreach ($symbols as $symbol) {
            $realtime = $realtime_prices[$symbol] ?? null;
            if ($realtime) {
                $positions[] = [
                    'symbol' => $symbol,
                    'price' => $realtime['price'],
                    'price_24h_ago' => null,
                    'change_24h' => $realtime['change_24h'],
                    'volume_24h' => $realtime['volume_24h'],
                    'volatility' => null,
                    'rsi' => null,
                    'atr' => null,
                    'macd' => null,
                    'timestamp' => $realtime['timestamp'],
                    'realtime' => true,
                    'open_trades' => $open_trades[$symbol] ?? []
                ];
            }
        }
    }
    
    jsonResponse(['positions' => $positions]);
    } catch (Exception $e) {
        error_log("Error in getPositions: " . $e->getMessage());
        error_log("Stack trace: " . $e->getTraceAsString());
        jsonResponse(['error' => 'Ошибка получения позиций: ' . $e->getMessage(), 'positions' => []], 200);
    }
}

function getStats() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'stats' => []], 200);
        }
    
    $stats = [];
    
    // Статистика по сделкам (общая)
    $query = "
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl
        FROM trades_history
        WHERE entry_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        AND status = 'closed'
    ";
    
    $stmt = $conn->query($query);
    if ($stmt && $row = $stmt->fetch()) {
        $stats['trades_24h'] = [
            'total' => intval($row['total_trades']),
            'winning' => intval($row['winning_trades']),
            'losing' => intval($row['losing_trades']),
            'total_pnl' => floatval($row['total_pnl'] ?? 0),
            'avg_pnl' => floatval($row['avg_pnl'] ?? 0),
            'win_rate' => $row['total_trades'] > 0 ? 
                (intval($row['winning_trades']) / intval($row['total_trades']) * 100) : 0
        ];
    }
    
    // Статистика по ботам (отдельно для каждого)
    $query = "
        SELECT 
            bot_name,
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl,
            COUNT(CASE WHEN status = 'open' THEN 1 END) as open_trades,
            COUNT(CASE WHEN status = 'closed' AND pnl IS NOT NULL THEN 1 END) as closed_trades
        FROM trades_history
        WHERE entry_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY bot_name
    ";
    
    $stmt = $conn->query($query);
    $bots_stats = [];
    if ($stmt) {
        while ($row = $stmt->fetch()) {
            $bot_name = $row['bot_name'] ?? 'main';
            $closed_count = intval($row['closed_trades']);
            $winning_count = intval($row['winning_trades']);
            $win_rate = $closed_count > 0 ? ($winning_count / $closed_count * 100) : 0;
            
            $bots_stats[$bot_name] = [
                'total_trades' => intval($row['total_trades']),
                'winning_trades' => $winning_count,
                'losing_trades' => intval($row['losing_trades']),
                'total_pnl' => floatval($row['total_pnl'] ?? 0),
                'avg_pnl' => floatval($row['avg_pnl'] ?? 0),
                'win_rate' => $win_rate,
                'open_trades' => intval($row['open_trades']),
                'closed_trades' => $closed_count
            ];
        }
    }
    $stats['bots'] = $bots_stats;
    
    // Статистика по AI ответам
    $query = "
        SELECT 
            COUNT(*) as total_responses,
            AVG(confidence) as avg_confidence,
            COUNT(DISTINCT recommended_symbol) as unique_symbols
        FROM ai_responses
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    ";
    
    $stmt = $conn->query($query);
    if ($stmt && $row = $stmt->fetch()) {
        $stats['ai_24h'] = [
            'total_responses' => intval($row['total_responses']),
            'avg_confidence' => floatval($row['avg_confidence'] ?? 0),
            'unique_symbols' => intval($row['unique_symbols'])
        ];
    }
    
    // Статистика по ошибкам
    $query = "
        SELECT COUNT(*) as error_count
        FROM api_errors
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    ";
    
    $stmt = $conn->query($query);
    if ($stmt && $row = $stmt->fetch()) {
        $stats['errors_24h'] = intval($row['error_count']);
    }
    
    // Статистика по данным в БД
    $query = "
        SELECT 
            COUNT(DISTINCT symbol) as symbols_count,
            COUNT(*) as total_records
        FROM market_history
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    ";
    
    $stmt = $conn->query($query);
    if ($stmt && $row = $stmt->fetch()) {
        $stats['database'] = [
            'symbols_count' => intval($row['symbols_count']),
            'total_records_7d' => intval($row['total_records'])
        ];
    }
    
        jsonResponse(['stats' => $stats]);
    } catch (Exception $e) {
        error_log("Error in getStats: " . $e->getMessage());
        jsonResponse(['error' => 'Ошибка получения статистики', 'stats' => []], 200);
    }
}

function getRecentTrades() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'trades' => []], 200);
        }
    
    $limit = intval($_GET['limit'] ?? 15);
    $offset = intval($_GET['offset'] ?? 0);
    $bot_name = $_GET['bot'] ?? null; // Фильтр по боту (main/iliya)
    
    // Сначала получаем общее количество для пагинации
    $countQuery = "SELECT COUNT(*) as total FROM trades_history WHERE 1=1";
    $countParams = [];
    if ($bot_name && $bot_name !== 'all') {
        $countQuery .= " AND bot_name = ?";
        $countParams[] = $bot_name;
    }
    $countStmt = $conn->prepare($countQuery);
    if ($countParams) {
        $countStmt->execute($countParams);
    } else {
        $countStmt->execute();
    }
    $totalCount = $countStmt->fetch()['total'] ?? 0;
    
    $query = "
        SELECT 
            bot_name,
            symbol,
            side,
            entry_price,
            exit_price,
            quantity,
            pnl,
            pnl_percent,
            leverage,
            status,
            entry_time as timestamp,
            exit_time
        FROM trades_history
        WHERE 1=1
    ";
    
    $params = [];
    if ($bot_name) {
        $query .= " AND bot_name = :bot_name";
        $params[':bot_name'] = $bot_name;
    }
    
    $query .= " ORDER BY entry_time DESC LIMIT :limit";
    $params[':limit'] = $limit;
    
    $stmt = $conn->prepare($query);
    foreach ($params as $key => $value) {
        if ($key === ':limit') {
            $stmt->bindValue($key, $value, PDO::PARAM_INT);
        } else {
            $stmt->bindValue($key, $value, PDO::PARAM_STR);
        }
    }
    $stmt->execute();
    
    $trades = [];
    while ($row = $stmt->fetch()) {
        $trades[] = [
            'bot_name' => $row['bot_name'] ?? 'main',
            'symbol' => $row['symbol'],
            'side' => $row['side'],
            'entry_price' => floatval($row['entry_price']),
            'exit_price' => $row['exit_price'] ? floatval($row['exit_price']) : null,
            'quantity' => floatval($row['quantity']),
            'pnl' => $row['pnl'] ? floatval($row['pnl']) : null,
            'pnl_percent' => $row['pnl_percent'] ? floatval($row['pnl_percent']) : null,
            'leverage' => $row['leverage'] ? intval($row['leverage']) : null,
            'status' => $row['status'] ?? 'open',
            'timestamp' => $row['timestamp'],
            'exit_time' => $row['exit_time']
        ];
    }
    
        jsonResponse(['trades' => $trades, 'total' => $totalCount]);
    } catch (Exception $e) {
        error_log("Error in getRecentTrades: " . $e->getMessage());
        jsonResponse(['error' => 'Ошибка получения сделок', 'trades' => []], 200);
    }
}

function formatAIContentValue($value) {
    if (is_array($value)) {
        return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    }
    return trim((string)$value);
}

function buildAIChatBlocks($row, $responseText, $fullResponse) {
    $blocks = [];
    
    if (!empty($row['prompt'])) {
        $blocks[] = [
            'role' => 'user',
            'title' => 'USER_PROMPT',
            'content' => trim($row['prompt'])
        ];
    }
    
    if (is_array($fullResponse) && !empty($fullResponse)) {
        foreach ($fullResponse as $key => $value) {
            if ($value === null || $value === '') {
                continue;
            }
            if ($key === 'analysis' && !empty($responseText)) {
                continue;
            }
            
            $blocks[] = [
                'role' => 'assistant',
                'title' => strtoupper(str_replace('_', ' ', $key)),
                'content' => formatAIContentValue($value)
            ];
        }
    }
    
    if (!empty($responseText)) {
        $blocks[] = [
            'role' => 'assistant',
            'title' => 'TRADING_DECISIONS',
            'content' => trim($responseText)
        ];
    }
    
    if (empty($blocks)) {
        $blocks[] = [
            'role' => 'assistant',
            'title' => 'AI_RESPONSE',
            'content' => $responseText ?: 'Нет данных'
        ];
    }
    
    return $blocks;
}

function getAIResponses() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'responses' => []], 200);
        }
    
    $limit = intval($_GET['limit'] ?? 15);
    $offset = intval($_GET['offset'] ?? 0);
    
    // Получаем общее количество для пагинации
    $countQuery = "SELECT COUNT(*) as total FROM ai_responses";
    $countStmt = $conn->query($countQuery);
    $totalCount = $countStmt->fetch()['total'] ?? 0;
    
    $query = "
        SELECT 
            timestamp,
            request_type,
            symbols,
            prompt,
            recommended_symbol,
            recommended_side,
            entry_price,
            stop_loss,
            take_profit,
            confidence,
            reasoning,
            full_response
        FROM ai_responses
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    ";
    
    $stmt = $conn->prepare($query);
    $stmt->bindValue(1, $limit, PDO::PARAM_INT);
    $stmt->bindValue(2, $offset, PDO::PARAM_INT);
    $stmt->execute();
    
    $responses = [];
    while ($row = $stmt->fetch()) {
        $fullResponse = [];
        if (!empty($row['full_response'])) {
            $decoded = json_decode($row['full_response'], true);
            if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) {
                $fullResponse = $decoded;
            }
        }
        
        $responseText = $row['reasoning'] ?? '';
        if (!$responseText && !empty($fullResponse)) {
            if (!empty($fullResponse['analysis'])) {
                $responseText = $fullResponse['analysis'];
            } elseif (!empty($fullResponse['reasoning'])) {
                $responseText = $fullResponse['reasoning'];
            } else {
                $responseText = json_encode($fullResponse, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
            }
        } elseif (!$responseText && !empty($row['full_response'])) {
            $responseText = $row['full_response'];
        }
        
        $symbolsRaw = $row['symbols'] ?? '';
        $symbolsList = [];
        if (!empty($symbolsRaw)) {
            $symbolsList = array_filter(array_map('trim', explode(',', $symbolsRaw)));
        }
        
        $responses[] = [
            'id' => $row['id'] ?? null,
            'timestamp' => $row['timestamp'],
            'request_type' => $row['request_type'],
            'symbols' => array_values($symbolsList),
            'prompt' => $row['prompt'],
            'symbol' => $row['recommended_symbol'],
            'side' => $row['recommended_side'],
            'entry_price' => $row['entry_price'] ? floatval($row['entry_price']) : null,
            'stop_loss' => $row['stop_loss'] ? floatval($row['stop_loss']) : null,
            'take_profit' => $row['take_profit'] ? floatval($row['take_profit']) : null,
            'confidence' => $row['confidence'] !== null ? floatval($row['confidence']) : null,
            'response_text' => $responseText,
            'chat_blocks' => buildAIChatBlocks($row, $responseText, $fullResponse)
        ];
    }
    
        jsonResponse(['responses' => $responses, 'total' => $totalCount]);
    } catch (Exception $e) {
        error_log("Error in getAIResponses: " . $e->getMessage());
        jsonResponse(['error' => 'Ошибка получения AI ответов', 'responses' => []], 200);
    }
}

function getRecentErrors() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'errors' => []], 200);
        }
    
    $limit = intval($_GET['limit'] ?? 15);
    $offset = intval($_GET['offset'] ?? 0);
    
    // Получаем общее количество для пагинации
    $countQuery = "SELECT COUNT(*) as total FROM api_errors";
    $countStmt = $conn->query($countQuery);
    $totalCount = $countStmt->fetch()['total'] ?? 0;
    
    $query = "
        SELECT 
            api_method,
            symbol,
            error_code,
            error_message,
            timestamp
        FROM api_errors
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    ";
    
    $stmt = $conn->prepare($query);
    $stmt->bindValue(1, $limit, PDO::PARAM_INT);
    $stmt->bindValue(2, $offset, PDO::PARAM_INT);
    $stmt->execute();
    
    $errors = [];
    while ($row = $stmt->fetch()) {
        $errors[] = [
            'api_method' => $row['api_method'],
            'symbol' => $row['symbol'],
            'error_code' => $row['error_code'],
            'error_message' => $row['error_message'],
            'timestamp' => $row['timestamp']
        ];
    }
    
        jsonResponse(['errors' => $errors, 'total' => $totalCount]);
    } catch (Exception $e) {
        error_log("Error in getRecentErrors: " . $e->getMessage());
        jsonResponse(['error' => 'Ошибка получения ошибок', 'errors' => []], 200);
    }
}

function getMarketData() {
    try {
        $conn = getDBConnection();
        if (!$conn) {
            jsonResponse(['error' => 'Ошибка подключения к БД', 'data' => []], 200);
        }
    
    $symbol = $_GET['symbol'] ?? 'BTCUSDT';
    $hours = intval($_GET['hours'] ?? 24);
    
    $query = "
        SELECT 
            timestamp,
            price,
            volume_24h,
            volatility,
            rsi,
            atr,
            macd
        FROM market_history
        WHERE symbol = :symbol 
        AND timestamp >= DATE_SUB(NOW(), INTERVAL :hours HOUR)
        ORDER BY timestamp DESC
        LIMIT 1000
    ";
    
    $stmt = $conn->prepare($query);
    $stmt->bindValue(':symbol', $symbol, PDO::PARAM_STR);
    $stmt->bindValue(':hours', $hours, PDO::PARAM_INT);
    $stmt->execute();
    
    $data = [];
    while ($row = $stmt->fetch()) {
        $data[] = [
            'timestamp' => $row['timestamp'],
            'price' => floatval($row['price']),
            'volume' => floatval($row['volume_24h']),
            'volatility' => floatval($row['volatility']),
            'rsi' => $row['rsi'] ? floatval($row['rsi']) : null,
            'atr' => $row['atr'] ? floatval($row['atr']) : null,
            'macd' => $row['macd'] ? floatval($row['macd']) : null
        ];
    }
    
        jsonResponse(['data' => array_reverse($data)]); // От старых к новым для графиков
    } catch (Exception $e) {
        error_log("Error in getMarketData: " . $e->getMessage());
        jsonResponse(['error' => 'Ошибка получения рыночных данных', 'data' => []], 200);
    }
}

