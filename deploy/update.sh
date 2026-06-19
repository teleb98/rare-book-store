#!/usr/bin/env bash
# 맥미니 서버에 최신 코드 배포: git pull → 의존성 갱신 → gunicorn 재시작
set -euo pipefail

APP_DIR="$HOME/rare-book-store"
cd "$APP_DIR"

echo "==> git pull"
git pull --ff-only

echo "==> 의존성 갱신"
./venv/bin/pip install -q -r requirements.txt

echo "==> gunicorn 재시작"
launchctl kickstart -k "gui/$(id -u)/com.rarebook.web"

sleep 3
echo "==> 헬스 체크"
curl -s -o /dev/null -w "local  http://127.0.0.1:8000/  -> HTTP %{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "public https://rarebook.co.kr/  -> HTTP %{http_code}\n" -L --max-time 20 https://rarebook.co.kr/ || true
echo "완료."
