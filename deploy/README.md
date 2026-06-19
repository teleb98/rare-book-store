# 맥미니 셀프호스팅 배포 가이드 (rarebook.co.kr)

이 디렉터리는 Rare Book Store(Flask 앱)를 **집에 있는 맥미니에서 직접 운영**하고,
`rarebook.co.kr` 도메인을 **Cloudflare Tunnel**로 연결하는 구성을 담고 있습니다.

```
방문자 → rarebook.co.kr (Cloudflare DNS + Universal SSL)
        → Cloudflare Tunnel (서울 엣지)
        → 맥미니 cloudflared (launchd)
        → gunicorn 127.0.0.1:8000 (launchd)
        → Flask 앱
        → 로컬 PostgreSQL
```

이 방식의 장점: 공유기 포트포워딩·고정 IP 불필요, 한국 ISP의 80/443 차단·CGNAT 우회,
HTTPS 인증서 자동 발급/갱신.

---

## 사전 준비

- Apple Silicon 맥미니 + [Homebrew](https://brew.sh)
- `rarebook.co.kr` 도메인 (한국 등록대행사에서 등록)
- 무료 [Cloudflare](https://dash.cloudflare.com) 계정

## 1. 패키지 설치

```bash
brew install postgresql@16 python@3.12 cloudflared
brew services start postgresql@16
```

## 2. 데이터베이스 생성

```bash
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
psql -d postgres -c "CREATE ROLE rarebooks LOGIN PASSWORD '강력한_비밀번호';"
psql -d postgres -c "CREATE DATABASE rarebooks OWNER rarebooks;"
```

## 3. 앱 설치 & 환경변수

```bash
cd ~/rare-book-store
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt

cp deploy/.env.example .env   # 값 채우기 (DATABASE_URL, SECRET_KEY, ADMIN_PASSWORD 등)
```

`SECRET_KEY`, `ADMIN_PASSWORD`는 다음으로 생성:

```bash
openssl rand -hex 32   # SECRET_KEY
openssl rand -hex 8    # ADMIN_PASSWORD 용
```

## 4. gunicorn 자동시작 (launchd)

```bash
cp deploy/com.rarebook.web.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.rarebook.web.plist
curl -I http://127.0.0.1:8000/   # HTTP 200 확인
```

## 5. 도메인을 Cloudflare로 연결

1. Cloudflare 대시보드 → **Add a domain** → `rarebook.co.kr` (Free 플랜)
2. 안내받은 네임서버 2개를 **등록대행사에서 교체**
3. 대시보드 상태가 **Active** 가 될 때까지 대기

## 6. Cloudflare Tunnel 생성

```bash
cloudflared tunnel login                         # 브라우저에서 도메인 Authorize
cloudflared tunnel create rarebook               # 터널 + 자격증명(json) 생성

cp deploy/cloudflared-config.example.yml ~/.cloudflared/config.yml
# config.yml 의 <TUNNEL_ID> 를 실제 값으로 교체 (cloudflared tunnel list 로 확인)

cloudflared tunnel route dns --overwrite-dns rarebook rarebook.co.kr
cloudflared tunnel route dns --overwrite-dns rarebook www.rarebook.co.kr
```

## 7. 터널 자동시작 (launchd)

```bash
cp deploy/com.rarebook.tunnel.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.rarebook.tunnel.plist
```

몇 분 후 Cloudflare Universal SSL이 발급되면 `https://rarebook.co.kr` 접속 완료.

---

## 운영

### 코드 업데이트 배포

```bash
deploy/update.sh        # git pull + 의존성 갱신 + gunicorn 재시작
```

또는 수동:

```bash
cd ~/rare-book-store && git pull
./venv/bin/pip install -r requirements.txt
launchctl kickstart -k gui/$(id -u)/com.rarebook.web
```

### 서비스 상태 / 로그

```bash
launchctl list | grep rarebook
tail -f logs/gunicorn.err.log
tail -f logs/cloudflared.err.log
```

### 주의 — 깃에 올리면 안 되는 것

`.env`, `~/.cloudflared/*.json`(터널 자격증명), `~/.cloudflared/cert.pem` 은
**절대 커밋하지 마세요.** (`.gitignore` 로 `.env` 는 이미 제외됨)
