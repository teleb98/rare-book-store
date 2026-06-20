"""
SMTP 이메일 발송 헬퍼.

환경변수(SMTP_HOST 등)가 설정되지 않으면 is_email_configured()가 False가 되고
send_email()은 조용히 False를 반환한다 — 미설정 상태에서도 앱은 정상 동작하며,
입고 알림은 "발송 대기" 상태로 남아 관리자가 수동으로 처리할 수 있다.

Gmail 사용 예 (.env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=chiwon@gmail.com
    SMTP_PASS=<Google 앱 비밀번호 16자리>   # 일반 비밀번호 아님. myaccount.google.com > 보안 > 앱 비밀번호
    SMTP_FROM_NAME=Rare Book Store
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr


def is_email_configured() -> bool:
    return all(os.environ.get(k, '').strip() for k in ('SMTP_HOST', 'SMTP_USER', 'SMTP_PASS'))


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """단건 이메일 발송. 성공 시 True, 미설정/실패 시 False."""
    if not is_email_configured():
        return False

    host = os.environ['SMTP_HOST'].strip()
    port = int(os.environ.get('SMTP_PORT', '587').strip() or 587)
    user = os.environ['SMTP_USER'].strip()
    password = os.environ['SMTP_PASS'].strip()
    from_addr = os.environ.get('SMTP_FROM', user).strip()
    from_name = os.environ.get('SMTP_FROM_NAME', 'Rare Book Store').strip()

    msg = MIMEText(html_body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = formataddr((from_name, from_addr))
    msg['To'] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"이메일 발송 실패 ({to_email}): {e}")
        return False
