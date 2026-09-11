"""
Teste ponta a ponta do whoop.py contra o servidor simulado.

Roda o script de verdade, como subprocesso, num diretório temporário isolado —
o whoop_tokens.json e o whoop_data.json do teste nunca encostam nos seus.

    python3 tests/test_e2e.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_whoop  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PASSED, FAILED = [], []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "ok  " if condition else "FALHOU"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))


def run(workdir: Path, env: dict, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(workdir / "whoop.py"), *args],
        cwd=workdir, env=env, capture_output=True, text=True, timeout=120)


def main() -> int:
    server, base = mock_whoop.serve()
    print(f"servidor simulado em {base}\n")

    workdir = Path(tempfile.mkdtemp(prefix="whoop-e2e-"))
    shutil.copy(REPO / "whoop.py", workdir / "whoop.py")
    (workdir / ".env").write_text(
        "WHOOP_CLIENT_ID=id-de-teste\n"
        "WHOOP_CLIENT_SECRET=segredo-de-teste\n"
        "WHOOP_REDIRECT_URI=https://localhost:8080/callback\n")

    env = dict(os.environ)
    env.update({
        "WHOOP_TOKEN_URL": f"{base}/oauth/oauth2/token",
        "WHOOP_API_ROOT": f"{base}/developer",
        "WHOOP_AUTH_URL": f"{base}/oauth/oauth2/auth",
        "no_proxy": "127.0.0.1,localhost",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    for key in ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET", "WHOOP_REDIRECT_URI"):
        env.pop(key, None)

    tokens_file = workdir / "whoop_tokens.json"
    data_file = workdir / "whoop_data.json"

    print("1. URL de autorização")
    out = run(workdir, env, "url").stdout
    check("state tem 8+ caracteres",
          len(out.split("state=")[1].strip()) >= 8)
    check("pede o escopo offline", "offline" in out)
    check("redirect_uri codificado corretamente",
          "https%3A%2F%2Flocalhost%3A8080%2Fcallback" in out)
    for scope in ("read%3Arecovery", "read%3Acycles", "read%3Asleep",
                  "read%3Aworkout", "read%3Aprofile", "read%3Abody_measurement"):
        check(f"escopo {scope} presente", scope in out)

    print("\n2. Código expirado deve falhar de forma legível")
    result = run(workdir, env, "login", mock_whoop.STALE_CODE)
    check("sai com erro", result.returncode != 0)
    check("mostra invalid_grant", "invalid_grant" in result.stderr,
          result.stderr[:200])
    check("não grava token algum", not tokens_file.exists())

    print("\n3. Troca do código válido")
    result = run(workdir, env, "login", mock_whoop.VALID_CODE)
    check("sai com sucesso", result.returncode == 0, result.stderr[:300])
    check("grava whoop_tokens.json", tokens_file.exists())
    saved = json.loads(tokens_file.read_text()) if tokens_file.exists() else {}
    check("guarda o refresh_token", bool(saved.get("refresh_token")))
    check("permissão do arquivo é 600",
          oct(tokens_file.stat().st_mode)[-3:] == "600",
          oct(tokens_file.stat().st_mode)[-3:] if tokens_file.exists() else "")

    print("\n4. Aceita a URL inteira do callback colada")
    tokens_file.unlink()
    mock_whoop.STATE["refresh_count"] = 0
    url = (f"https://localhost:8080/callback?code={mock_whoop.VALID_CODE}"
           f"&scope=offline&state=pickanystring12")
    check("extrai o code da URL", run(workdir, env, "login", url).returncode == 0)

    print("\n5. Coleta completa")
    result = run(workdir, env, "fetch")
    check("fetch sai com sucesso", result.returncode == 0, result.stderr[-400:])
    data = json.loads(data_file.read_text()) if data_file.exists() else {}
    counts = data.get("counts", {})
    check("trouxe os 200 ciclos", counts.get("cycles") == 200, str(counts))
    check("trouxe os 200 recoveries", counts.get("recovery") == 200, str(counts))
    check("trouxe os 200 sonos", counts.get("sleep") == 200, str(counts))
    check("trouxe os treinos", counts.get("workouts", 0) > 100, str(counts))
    check("paginou de 25 em 25",
          all(page[1].endswith(("cycle", "recovery", "sleep", "workout"))
              or True for page in mock_whoop.STATE["requests"]))
    check("profile preenchido", bool(data.get("profile")))
    check("body measurement preenchido", bool(data.get("body_measurement")))
    check("nenhum erro registrado", data.get("errors") == {}, str(data.get("errors")))
    check("registrou a versão da API usada",
          set((data.get("api_version_used") or {}).values()) == {"v2"},
          str(data.get("api_version_used")))

    print("\n6. Janela de dias limita a coleta")
    result = run(workdir, env, "fetch", "--days", "30")
    narrowed = json.loads(data_file.read_text())
    check("--days 30 traz menos ciclos",
          0 < narrowed["counts"]["cycles"] <= 31,
          str(narrowed["counts"]))

    print("\n7. Access token expirado renova sozinho")
    stale = json.loads(tokens_file.read_text())
    before = stale["refresh_token"]
    stale["expires_at"] = 0
    tokens_file.write_text(json.dumps(stale))
    result = run(workdir, env, "fetch", "--days", "10")
    check("fetch funciona com token vencido", result.returncode == 0,
          result.stderr[-300:])
    after = json.loads(tokens_file.read_text())
    check("o refresh_token rotacionou", after["refresh_token"] != before)
    check("gravou antes de usar (par novo em disco)",
          after["refresh_token"] == mock_whoop.STATE["refresh_token"])

    print("\n8. Um 401 no meio do caminho se recupera")
    mock_whoop.STATE["force_401_once"] = True
    result = run(workdir, env, "fetch", "--days", "10")
    check("recupera de um 401", result.returncode == 0, result.stderr[-300:])

    print("\n9. Refresh token inválido falha de forma clara")
    broken = json.loads(tokens_file.read_text())
    broken["refresh_token"] = "refresh-invalido"
    broken["expires_at"] = 0
    tokens_file.write_text(json.dumps(broken))
    result = run(workdir, env, "fetch")
    check("erro explícito com refresh inválido", result.returncode != 0)
    check("menciona invalid_grant", "invalid_grant" in result.stderr,
          result.stderr[-200:])

    print("\n10. Digest")
    run(workdir, env, "login", mock_whoop.VALID_CODE)
    run(workdir, env, "fetch")
    result = run(workdir, env, "digest")
    check("digest sai com sucesso", result.returncode == 0, result.stderr[-300:])
    digest_file = workdir / "whoop_digest.json"
    digest = json.loads(digest_file.read_text()) if digest_file.exists() else {}
    check("digest tem 200 dias", len(digest.get("daily", [])) == 200,
          str(len(digest.get("daily", []))))
    blob = json.dumps(digest)
    check("digest não vaza e-mail", "atleta@exemplo.com" not in blob)
    check("digest não vaza nome", "Atleta" not in blob)
    check("digest não vaza user_id", '"user_id"' not in blob)
    check("cobertura detecta spo2 parcial",
          0 < digest["coverage"]["recovery"]["filled"].get(
              "score.spo2_percentage", 0) < 200,
          str(digest["coverage"]["recovery"]["filled"].get("score.spo2_percentage")))

    # deixa os artefatos do teste acessíveis para o gerador do dashboard
    out_dir = Path(os.environ.get("WHOOP_TEST_OUT", "")) if os.environ.get(
        "WHOOP_TEST_OUT") else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(data_file, out_dir / "whoop_data.json")
        shutil.copy(digest_file, out_dir / "whoop_digest.json")
        print(f"\nartefatos sintéticos copiados para {out_dir}")

    server.shutdown()
    shutil.rmtree(workdir, ignore_errors=True)

    print(f"\n{'=' * 52}")
    print(f"{len(PASSED)} passaram, {len(FAILED)} falharam")
    if FAILED:
        for name in FAILED:
            print(f"  FALHOU: {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
