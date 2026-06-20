"""
카카오 / 네이버 / 구글 소셜 로그인 공용 OAuth 헬퍼.

각 제공자의 Client ID/Secret이 .env에 설정되어 있지 않으면 해당 제공자는
조용히 비활성화된다 (is_provider_configured == False) — 라우트와 템플릿에서
이를 확인해 버튼을 숨기거나 에러를 안내한다.
"""
import os
import requests

PROVIDERS = {
    'kakao': {
        'authorize_url': 'https://kauth.kakao.com/oauth/authorize',
        'token_url': 'https://kauth.kakao.com/oauth/token',
        'userinfo_url': 'https://kapi.kakao.com/v2/user/me',
        # 카카오 로그인은 책 검색에 쓰는 REST API 키를 그대로 client_id로 사용한다.
        'client_id_env': 'KAKAO_REST_API_KEY',
        'client_secret_env': 'KAKAO_CLIENT_SECRET',  # 선택 사항 (카카오 콘솔에서 활성화 시에만 필요)
        'scope': None,
    },
    'naver': {
        'authorize_url': 'https://nid.naver.com/oauth2.0/authorize',
        'token_url': 'https://nid.naver.com/oauth2.0/token',
        'userinfo_url': 'https://openapi.naver.com/v1/nid/me',
        'client_id_env': 'NAVER_CLIENT_ID',
        'client_secret_env': 'NAVER_CLIENT_SECRET',
        'scope': None,
    },
    'google': {
        'authorize_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'userinfo_url': 'https://www.googleapis.com/oauth2/v3/userinfo',
        # Gemini용 GOOGLE_API_KEY와는 별개의 OAuth 클라이언트가 필요하다.
        'client_id_env': 'GOOGLE_OAUTH_CLIENT_ID',
        'client_secret_env': 'GOOGLE_OAUTH_CLIENT_SECRET',
        'scope': 'openid email profile',
    },
}


def get_redirect_uri(provider: str) -> str:
    base = os.environ.get('OAUTH_REDIRECT_BASE_URL', 'https://rarebook.co.kr').rstrip('/')
    return f"{base}/auth/{provider}/callback"


def is_provider_configured(provider: str) -> bool:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return False
    return bool(os.environ.get(cfg['client_id_env'], '').strip())


def build_authorize_url(provider: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    params = {
        'client_id': os.environ.get(cfg['client_id_env'], ''),
        'redirect_uri': get_redirect_uri(provider),
        'response_type': 'code',
        'state': state,
    }
    if cfg.get('scope'):
        params['scope'] = cfg['scope']
    return requests.Request('GET', cfg['authorize_url'], params=params).prepare().url


def exchange_code_for_profile(provider: str, code: str) -> dict:
    """인가 코드를 액세스 토큰으로 교환하고, 사용자 프로필(provider_id/email/name)을 반환한다."""
    cfg = PROVIDERS[provider]
    client_id = os.environ.get(cfg['client_id_env'], '')
    client_secret = os.environ.get(cfg['client_secret_env'], '')

    token_data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'redirect_uri': get_redirect_uri(provider),
        'code': code,
    }
    if client_secret:
        token_data['client_secret'] = client_secret

    token_resp = requests.post(
        cfg['token_url'], data=token_data,
        headers={'Accept': 'application/json'}, timeout=10
    )
    if not token_resp.ok:
        print(f"{provider} 토큰 교환 실패: status={token_resp.status_code} body={token_resp.text}")
    token_resp.raise_for_status()
    access_token = token_resp.json().get('access_token')
    if not access_token:
        raise ValueError(f"{provider}: 토큰 응답에 access_token이 없습니다.")

    headers = {'Authorization': f'Bearer {access_token}'}
    info_resp = requests.get(cfg['userinfo_url'], headers=headers, timeout=10)
    info_resp.raise_for_status()
    data = info_resp.json()

    if provider == 'naver':
        profile = data.get('response', {})
        return {
            'provider_id': profile.get('id'),
            'email': profile.get('email'),
            'name': profile.get('name') or profile.get('nickname') or '네이버 사용자',
        }
    if provider == 'kakao':
        account = data.get('kakao_account', {})
        nickname = account.get('profile', {}).get('nickname')
        return {
            'provider_id': str(data.get('id')) if data.get('id') is not None else None,
            'email': account.get('email'),
            'name': nickname or '카카오 사용자',
        }
    if provider == 'google':
        return {
            'provider_id': data.get('sub'),
            'email': data.get('email'),
            'name': data.get('name') or '구글 사용자',
        }
    return {}
