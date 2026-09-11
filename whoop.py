#!/usr/bin/env python3
"""
whoop.py — cliente OAuth2 + coletor de dados da API oficial do WHOOP.

Sem dependências externas: usa apenas a biblioteca padrão do Python 3.9+.

Uso:
    python3 whoop.py url                  # imprime a URL de autorização
    python3 whoop.py login <code>         # troca o code por access+refresh token
    python3 whoop.py refresh              # força a renovação do access token
    python3 whoop.py status               # mostra o estado atual dos tokens
    python3 whoop.py fetch [--days 365]   # baixa tudo para whoop_data.json

Arquivos gerados (todos no .gitignore):
    .env                -> credenciais (você cria a partir do .env.example)
    whoop_tokens.json   -> access_token / refresh_token / expiração
    whoop_data.json     -> dados brutos coletados da API
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

# --------------------------------------------------------------------------- #
# Constantes da API do WHOOP
# --------------------------------------------------------------------------- #

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_ROOT = "https://api.prod.whoop.com/developer"

# "offline" é o que garante o refresh_token. Sem ele, você teria de reautorizar
# no navegador a cada ~1 hora.
SCOPES = [
    "offline",
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
]

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
TOKEN_FILE = ROOT / "whoop_tokens.json"
DATA_FILE = ROOT / "whoop_data.json"

PAGE_LIMIT = 25          # máximo aceito pela API por página
REFRESH_MARGIN = 120     # renova o token 2 min antes de expirar
USER_AGENT = "whoop-dashboard/1.0 (+local script)"


# --------------------------------------------------------------------------- #
# .env
# --------------------------------------------------------------------------- #

def load_env() -> dict:
    """Lê o .env (formato KEY=VALUE) sem depender do python-dotenv."""
    env = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            env[key.strip()] = value
    # variáveis de ambiente reais têm precedência sobre o arquivo
    for key in ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET", "WHOOP_REDIRECT_URI"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def credentials(require_secret: bool = True) -> tuple[str, str, str]:
    env = load_env()
    client_id = env.get("WHOOP_CLIENT_ID", "")
    client_secret = env.get("WHOOP_CLIENT_SECRET", "")
    redirect_uri = env.get("WHOOP_REDIRECT_URI", "https://localhost:8080/callback")
    required = [("WHOOP_CLIENT_ID", client_id)]
    if require_secret:
        required.append(("WHOOP_CLIENT_SECRET", client_secret))
    missing = [name for name, value in required if not value]
    if missing:
        die(
            f"Faltando no .env: {', '.join(missing)}.\n"
            f"Copie .env.example para .env e preencha os campos."
        )
    return client_id, client_secret, redirect_uri


def die(message: str, code: int = 1) -> NoReturn:
    print(f"ERRO: {message}", file=sys.stderr)
    raise SystemExit(code)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def http(
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    retries: int = 4,
) -> dict:
    """Requisição HTTP simples com retry em 429/5xx."""
    body = urllib.parse.urlencode(data).encode() if data else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    hdrs.update(headers or {})

    last_error = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            last_error = HttpError(exc.code, detail, url)
            if exc.code == 429:
                wait = float(exc.headers.get("Retry-After") or (2 ** attempt))
                time.sleep(min(wait, 60))
                continue
            if 500 <= exc.code < 600 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise last_error
        except urllib.error.URLError as exc:
            last_error = HttpError(0, str(exc.reason), url)
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise last_error
    raise last_error  # pragma: no cover


class HttpError(Exception):
    def __init__(self, status: int, detail: str, url: str):
        self.status = status
        self.detail = detail
        self.url = url
        super().__init__(f"HTTP {status} em {url}: {detail}")


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #

def save_tokens(payload: dict) -> dict:
    now = int(time.time())
    expires_in = int(payload.get("expires_in", 3600))
    record = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "token_type": payload.get("token_type", "bearer"),
        "scope": payload.get("scope", " ".join(SCOPES)),
        "obtained_at": now,
        "expires_in": expires_in,
        "expires_at": now + expires_in,
    }
    if not record["refresh_token"]:
        # em um refresh o WHOOP devolve um refresh_token novo; se não vier,
        # preserva o anterior para não perder o acesso offline.
        previous = read_tokens()
        record["refresh_token"] = previous.get("refresh_token", "") if previous else ""
    TOKEN_FILE.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return record


def read_tokens() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def exchange_code(code: str) -> dict:
    client_id, client_secret, redirect_uri = credentials()
    code = code.strip()
    if code.startswith("http"):  # tolera colar a URL inteira do callback
        query = urllib.parse.urlparse(code).query
        code = urllib.parse.parse_qs(query).get("code", [""])[0]
    if not code:
        die("Não encontrei nenhum 'code'. Cole o valor do parâmetro code= da URL.")
    payload = http(
        TOKEN_URL,
        method="POST",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )
    return save_tokens(payload)


def refresh_tokens() -> dict:
    client_id, client_secret, _ = credentials()
    tokens = read_tokens()
    if not tokens or not tokens.get("refresh_token"):
        die("Sem refresh_token salvo. Rode 'python3 whoop.py url' e autorize de novo.")
    payload = http(
        TOKEN_URL,
        method="POST",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "offline",
        },
    )
    return save_tokens(payload)


def access_token() -> str:
    """Devolve um access_token válido, renovando sozinho quando necessário."""
    tokens = read_tokens()
    if not tokens:
        die("Nenhum token salvo. Rode: python3 whoop.py url")
    if time.time() >= tokens["expires_at"] - REFRESH_MARGIN:
        print("· access token expirado/expirando — renovando…", file=sys.stderr)
        tokens = refresh_tokens()
    return tokens["access_token"]


def build_auth_url() -> str:
    client_id, _, redirect_uri = credentials(require_secret=False)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # a API do WHOOP exige um state de 8+ caracteres
        "state": secrets.token_urlsafe(16),
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


# --------------------------------------------------------------------------- #
# Coleta de dados
# --------------------------------------------------------------------------- #

def api_get(path: str, params: dict | None = None) -> dict:
    """GET autenticado. Tenta v2 e cai para v1 se o endpoint não existir."""
    token = access_token()
    headers = {"Authorization": f"Bearer {token}"}
    for version in ("v2", "v1"):
        url = f"{API_ROOT}/{version}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        try:
            return http(url, headers=headers)
        except HttpError as exc:
            if exc.status == 404 and version == "v2":
                continue  # tenta a v1
            if exc.status == 401:
                headers = {"Authorization": f"Bearer {refresh_tokens()['access_token']}"}
                return http(url, headers=headers)
            raise
    raise HttpError(404, "endpoint não encontrado em v2 nem v1", path)


def collect(path: str, start: str, end: str, label: str) -> list:
    """Percorre todas as páginas de uma coleção paginada."""
    records, next_token, page = [], None, 0
    while True:
        params = {"limit": PAGE_LIMIT, "start": start, "end": end}
        if next_token:
            params["nextToken"] = next_token
        payload = api_get(path, params)
        batch = payload.get("records", [])
        records.extend(batch)
        page += 1
        print(f"  {label}: {len(records)} registros (página {page})", file=sys.stderr)
        next_token = payload.get("next_token")
        if not next_token or not batch:
            break
        time.sleep(0.2)  # respeita o rate limit (100 req/min)
    return records


def fetch_all(days: int) -> dict:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    print(f"Coletando de {start_dt.date()} até {end_dt.date()} ({days} dias)…",
          file=sys.stderr)

    data = {
        "fetched_at": end_dt.isoformat(),
        "range": {"start": start, "end": end, "days": days},
        "errors": {},
    }

    singles = {
        "profile": "user/profile/basic",
        "body_measurement": "user/measurement/body",
    }
    for key, path in singles.items():
        try:
            data[key] = api_get(path)
            print(f"  {key}: ok", file=sys.stderr)
        except HttpError as exc:
            data[key] = None
            data["errors"][key] = str(exc)
            print(f"  {key}: FALHOU ({exc.status})", file=sys.stderr)

    collections = {
        "cycles": "cycle",
        "recovery": "recovery",
        "sleep": "activity/sleep",
        "workouts": "activity/workout",
    }
    for key, path in collections.items():
        try:
            data[key] = collect(path, start, end, key)
        except HttpError as exc:
            data[key] = []
            data["errors"][key] = str(exc)
            print(f"  {key}: FALHOU ({exc.status}) {exc.detail[:120]}", file=sys.stderr)

    data["counts"] = {
        key: len(data.get(key) or [])
        for key in ("cycles", "recovery", "sleep", "workouts")
    }
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return data


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def cmd_url(_args) -> None:
    url = build_auth_url()
    print("\n1. Abra esta URL no navegador (logado na sua conta WHOOP):\n")
    print(url)
    print(
        "\n2. Aprove o acesso.\n"
        "3. O navegador vai tentar abrir https://localhost:8080/callback?code=...\n"
        "   Vai dar erro de conexão — isso é esperado e não é problema.\n"
        "4. Copie o valor de code= da barra de endereço e rode em MENOS DE 1 MINUTO:\n"
        "      python3 whoop.py login <code>\n"
    )


def cmd_login(args) -> None:
    record = exchange_code(args.code)
    expires = datetime.fromtimestamp(record["expires_at"], timezone.utc)
    print(f"Tokens salvos em {TOKEN_FILE.name}")
    print(f"  scope        : {record['scope']}")
    print(f"  expira em    : {expires.isoformat()} (UTC)")
    print(f"  refresh_token: {'presente' if record['refresh_token'] else 'AUSENTE'}")
    print("\nAgora rode: python3 whoop.py fetch")


def cmd_refresh(_args) -> None:
    record = refresh_tokens()
    expires = datetime.fromtimestamp(record["expires_at"], timezone.utc)
    print(f"Token renovado. Novo vencimento: {expires.isoformat()} (UTC)")


def cmd_status(_args) -> None:
    tokens = read_tokens()
    if not tokens:
        print("Nenhum token salvo. Rode: python3 whoop.py url")
        return
    remaining = int(tokens["expires_at"] - time.time())
    print(f"scope        : {tokens.get('scope')}")
    print(f"refresh_token: {'presente' if tokens.get('refresh_token') else 'AUSENTE'}")
    print(f"access_token : {'válido' if remaining > 0 else 'expirado'} "
          f"({remaining}s restantes)")


def cmd_fetch(args) -> None:
    data = fetch_all(args.days)
    print("\nResumo:")
    for key, count in data["counts"].items():
        print(f"  {key:16s}: {count}")
    print(f"  profile         : {'ok' if data.get('profile') else 'vazio'}")
    print(f"  body_measurement: {'ok' if data.get('body_measurement') else 'vazio'}")
    if data["errors"]:
        print("\nErros:")
        for key, message in data["errors"].items():
            print(f"  {key}: {message}")
    print(f"\nArquivo salvo: {DATA_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente da API do WHOOP")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("url", help="imprime a URL de autorização").set_defaults(func=cmd_url)

    login = sub.add_parser("login", help="troca o código de autorização por tokens")
    login.add_argument("code", help="o valor de code= da URL de callback")
    login.set_defaults(func=cmd_login)

    sub.add_parser("refresh", help="renova o access token").set_defaults(func=cmd_refresh)
    sub.add_parser("status", help="estado dos tokens").set_defaults(func=cmd_status)

    fetch = sub.add_parser("fetch", help="baixa os dados para whoop_data.json")
    fetch.add_argument("--days", type=int, default=365,
                       help="quantos dias de histórico buscar (padrão: 365)")
    fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    try:
        args.func(args)
    except HttpError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
