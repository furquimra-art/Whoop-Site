"""
Servidor que imita a API do WHOOP, para testar o whoop.py sem rede e sem
consumir a conta real. Gera um histórico sintético determinístico.

Uso isolado:  python3 tests/mock_whoop.py 8099
"""

from __future__ import annotations

import json
import math
import random
import sys
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VALID_CODE = "code-fresco-valido"
STALE_CODE = "code-velho-expirado"

STATE = {
    "access_token": "",
    "refresh_token": "",
    "expires_in": 3600,
    "issued": 0,
    "refresh_count": 0,
    "force_401_once": False,
    "requests": [],
}


# --------------------------------------------------------------------------- #
# Histórico sintético
# --------------------------------------------------------------------------- #

def build_history(days: int = 200) -> dict:
    rnd = random.Random(42)
    today = datetime(2026, 9, 11, tzinfo=timezone.utc)
    cycles, recovery, sleep, workouts = [], [], [], []

    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        season = math.sin(offset / 14.0)
        cycle_id = 100000 + offset
        strain = round(max(2.0, min(20.9, 11.5 + season * 3.5 + rnd.gauss(0, 2.2))), 4)
        cycles.append({
            "id": cycle_id,
            "user_id": 555,
            "created_at": day.isoformat().replace("+00:00", ".000Z"),
            "updated_at": day.isoformat().replace("+00:00", ".000Z"),
            "start": day.replace(hour=6).isoformat().replace("+00:00", ".000Z"),
            "end": (day.replace(hour=6) + timedelta(days=1)).isoformat().replace(
                "+00:00", ".000Z"),
            "timezone_offset": "-03:00",
            "score_state": "SCORED",
            "score": {
                "strain": strain,
                "kilojoule": round(7000 + strain * 420 + rnd.gauss(0, 300), 2),
                "average_heart_rate": int(66 + strain * 1.1 + rnd.gauss(0, 3)),
                "max_heart_rate": int(150 + strain * 1.6 + rnd.gauss(0, 6)),
            },
        })

        rec_score = int(max(5, min(99, 62 - season * 14 + rnd.gauss(0, 13))))
        recovery.append({
            "cycle_id": cycle_id,
            "sleep_id": f"sleep-{offset}",
            "user_id": 555,
            "created_at": day.replace(hour=7).isoformat().replace("+00:00", ".000Z"),
            "updated_at": day.replace(hour=7).isoformat().replace("+00:00", ".000Z"),
            "score_state": "SCORED",
            "score": {
                "user_calibrating": offset > days - 12,
                "recovery_score": rec_score,
                "resting_heart_rate": int(54 - rec_score * 0.06 + rnd.gauss(0, 2)),
                "hrv_rmssd_milli": round(38 + rec_score * 0.35 + rnd.gauss(0, 5), 4),
                # spo2 e skin temp só existem em parte do histórico, de propósito
                "spo2_percentage": (round(95 + rnd.random() * 3, 4)
                                    if offset < 120 else None),
                "skin_temp_celsius": (round(33 + rnd.gauss(0, 0.4), 4)
                                      if offset < 120 else None),
            },
        })

        in_bed = int((6.6 + rnd.gauss(0, 1.0)) * 3600 * 1000)
        awake = int(in_bed * (0.05 + rnd.random() * 0.06))
        asleep = in_bed - awake
        sleep.append({
            "id": f"sleep-{offset}",
            "user_id": 555,
            "created_at": day.isoformat().replace("+00:00", ".000Z"),
            "updated_at": day.isoformat().replace("+00:00", ".000Z"),
            "start": (day.replace(hour=23) - timedelta(days=1)).isoformat().replace(
                "+00:00", ".000Z"),
            "end": (day.replace(hour=23) - timedelta(days=1)
                    + timedelta(milliseconds=in_bed)).isoformat().replace(
                "+00:00", ".000Z"),
            "timezone_offset": "-03:00",
            "nap": False,
            "score_state": "SCORED",
            "score": {
                "stage_summary": {
                    "total_in_bed_time_milli": in_bed,
                    "total_awake_time_milli": awake,
                    "total_no_data_time_milli": 0,
                    "total_light_sleep_time_milli": int(asleep * 0.53),
                    "total_slow_wave_sleep_time_milli": int(asleep * 0.20),
                    "total_rem_sleep_time_milli": int(asleep * 0.27),
                    "sleep_cycle_count": rnd.randint(3, 6),
                    "disturbance_count": rnd.randint(2, 18),
                },
                "sleep_needed": {
                    "baseline_milli": 27000000,
                    "need_from_sleep_debt_milli": rnd.randint(0, 4000000),
                    "need_from_recent_strain_milli": int(strain * 90000),
                    "need_from_recent_nap_milli": 0,
                },
                "respiratory_rate": round(14 + rnd.gauss(0, 0.8), 4),
                "sleep_performance_percentage": round(min(100, asleep / 28000000 * 100), 1),
                "sleep_consistency_percentage": rnd.randint(40, 90),
                "sleep_efficiency_percentage": round(asleep / in_bed * 100, 4),
            },
        })

        if offset % 7 in (0, 2, 4, 5):
            start = day.replace(hour=18)
            minutes = rnd.choice([35, 45, 50, 62, 75])
            sport = rnd.choice(["running", "weightlifting", "cycling", "functional_fitness"])
            workouts.append({
                "id": f"workout-{offset}",
                "user_id": 555,
                "created_at": start.isoformat().replace("+00:00", ".000Z"),
                "updated_at": start.isoformat().replace("+00:00", ".000Z"),
                "start": start.isoformat().replace("+00:00", ".000Z"),
                "end": (start + timedelta(minutes=minutes)).isoformat().replace(
                    "+00:00", ".000Z"),
                "timezone_offset": "-03:00",
                "sport_name": sport,
                "score_state": "SCORED",
                "score": {
                    "strain": round(strain * 0.72, 4),
                    "average_heart_rate": int(132 + rnd.gauss(0, 8)),
                    "max_heart_rate": int(168 + rnd.gauss(0, 7)),
                    "kilojoule": round(minutes * 32 + rnd.gauss(0, 80), 2),
                    "percent_recorded": 100.0,
                    "distance_meter": (round(minutes * 175 + rnd.gauss(0, 300), 1)
                                       if sport in ("running", "cycling") else None),
                    "altitude_gain_meter": None,
                    "altitude_change_meter": None,
                    "zone_duration": {
                        "zone_zero_milli": 0,
                        "zone_one_milli": int(minutes * 60000 * 0.15),
                        "zone_two_milli": int(minutes * 60000 * 0.35),
                        "zone_three_milli": int(minutes * 60000 * 0.30),
                        "zone_four_milli": int(minutes * 60000 * 0.15),
                        "zone_five_milli": int(minutes * 60000 * 0.05),
                    },
                },
            })

    return {"cycle": cycles, "recovery": recovery,
            "activity/sleep": sleep, "activity/workout": workouts}


HISTORY = build_history()


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia o log padrão
        pass

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- OAuth ---------------------------------------------------------- #
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        grant = form.get("grant_type", [""])[0]
        STATE["requests"].append(("POST", self.path, grant))

        if not form.get("client_id", [""])[0]:
            return self._send(401, {"error": "invalid_client"})
        if not form.get("client_secret", [""])[0]:
            return self._send(401, {"error": "invalid_client"})

        if grant == "authorization_code":
            if form.get("code", [""])[0] != VALID_CODE:
                return self._send(400, {"error": "invalid_grant",
                                        "error_description": "code expired"})
            if form.get("redirect_uri", [""])[0] != "https://localhost:8080/callback":
                return self._send(400, {"error": "invalid_grant",
                                        "error_description": "redirect_uri mismatch"})
            return self._issue()

        if grant == "refresh_token":
            if form.get("refresh_token", [""])[0] != STATE["refresh_token"]:
                # o WHOOP rotaciona: o refresh antigo morre na hora
                return self._send(400, {"error": "invalid_grant",
                                        "error_description": "refresh token rotated"})
            STATE["refresh_count"] += 1
            return self._issue()

        return self._send(400, {"error": "unsupported_grant_type"})

    def _issue(self):
        serial = STATE["refresh_count"]
        STATE["access_token"] = f"access-{serial}"
        STATE["refresh_token"] = f"refresh-{serial}"
        return self._send(200, {
            "access_token": STATE["access_token"],
            "refresh_token": STATE["refresh_token"],
            "expires_in": STATE["expires_in"],
            "token_type": "bearer",
            "scope": ("offline read:recovery read:cycles read:sleep "
                      "read:workout read:profile read:body_measurement"),
        })

    # ---- Dados ---------------------------------------------------------- #
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        STATE["requests"].append(("GET", parsed.path, None))

        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {STATE['access_token']}":
            return self._send(401, {"error": "unauthorized"})
        if STATE["force_401_once"]:
            STATE["force_401_once"] = False
            return self._send(401, {"error": "unauthorized"})

        if not parsed.path.startswith("/developer/v2/"):
            return self._send(404, {"error": "not found"})
        resource = parsed.path[len("/developer/v2/"):]

        if resource == "user/profile/basic":
            return self._send(200, {"user_id": 555, "email": "atleta@exemplo.com",
                                    "first_name": "Atleta", "last_name": "Teste"})
        if resource == "user/measurement/body":
            return self._send(200, {"height_meter": 1.78, "weight_kilogram": 76.4,
                                    "max_heart_rate": 191})

        if resource not in HISTORY:
            return self._send(404, {"error": "not found"})

        records = HISTORY[resource]
        start, end = query.get("start", [None])[0], query.get("end", [None])[0]
        if start and end:
            records = [r for r in records
                       if start <= (r.get("start") or r.get("created_at")) <= end]

        limit = int(query.get("limit", ["25"])[0])
        if limit > 25:
            return self._send(400, {"error": "limit too large"})
        offset = int(query.get("nextToken", ["0"])[0])
        page = records[offset:offset + limit]
        following = offset + limit
        return self._send(200, {
            "records": page,
            "next_token": str(following) if following < len(records) else None,
        })


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    srv, base = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8099)
    print(f"mock WHOOP em {base}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
