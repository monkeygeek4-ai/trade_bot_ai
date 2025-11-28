#!/bin/bash
# Добавляем комментарии для code review в начало ключевых файлов

files=(
  "services/bybit_service.py"
  "services/db_service.py"
  "services/market_analysis_service.py"
  "services/news_service.py"
  "services/risk_management_service.py"
  "services/trading_decision_service.py"
  "monitor/index.php"
  "monitor/style.css"
  "config.py"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    # Проверяем, есть ли уже комментарий
    if ! grep -q "Code review" "$file" 2>/dev/null; then
      # Добавляем комментарий в начало файла
      if [[ "$file" == *.py ]]; then
        sed -i '' '1i\
# Code review marker
' "$file"
      elif [[ "$file" == *.php ]]; then
        sed -i '' '2i\
// Code review marker
' "$file"
      elif [[ "$file" == *.css ]]; then
        sed -i '' '1i\
/* Code review marker */
' "$file"
      fi
    fi
  fi
done
