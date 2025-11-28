<?php
/**
 * Конфигурация для системы мониторинга торгового бота
 */

// Настройки подключения к БД
define('DB_HOST', '85.198.119.37');
define('DB_PORT', '3306');
define('DB_NAME', 'bybit19');
define('DB_USER', 'bybit19_usr');
define('DB_PASSWORD', 'Rjhjkm432!');

// Настройки времени
date_default_timezone_set('UTC');

// Подключение к БД (используем PDO для совместимости)
function getDBConnection() {
    static $conn = null;
    
    if ($conn === null) {
        try {
            // Проверяем наличие драйвера PDO MySQL
            if (!in_array('mysql', PDO::getAvailableDrivers())) {
                error_log("PDO MySQL драйвер не установлен. Доступные драйверы: " . implode(', ', PDO::getAvailableDrivers()));
                throw new Exception("PDO MySQL драйвер не установлен. Установите: apt-get install php-mysql");
            }
            
            $dsn = "mysql:host=" . DB_HOST . ";port=" . DB_PORT . ";dbname=" . DB_NAME . ";charset=utf8mb4";
            $conn = new PDO($dsn, DB_USER, DB_PASSWORD);
            $conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $conn->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        } catch (PDOException $e) {
            error_log("Ошибка подключения к БД: " . $e->getMessage());
            return null;
        } catch (Exception $e) {
            error_log("Ошибка: " . $e->getMessage());
            return null;
        }
    }
    
    return $conn;
}

// Безопасный вывод JSON
function jsonResponse($data, $statusCode = 200) {
    http_response_code($statusCode);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// Безопасный вывод HTML
function escape($string) {
    return htmlspecialchars($string, ENT_QUOTES, 'UTF-8');
}

// Форматирование числа
function formatNumber($number, $decimals = 2) {
    return number_format($number, $decimals, '.', ' ');
}

// Форматирование процента
function formatPercent($number, $decimals = 2) {
    return number_format($number, $decimals, '.', ' ') . '%';
}

// Форматирование времени
function formatTime($timestamp) {
    return date('Y-m-d H:i:s', strtotime($timestamp));
}

// Форматирование времени назад
function timeAgo($timestamp) {
    $time = time() - strtotime($timestamp);
    
    if ($time < 60) return 'только что';
    if ($time < 3600) return floor($time / 60) . ' мин назад';
    if ($time < 86400) return floor($time / 3600) . ' ч назад';
    return floor($time / 86400) . ' дн назад';
}

