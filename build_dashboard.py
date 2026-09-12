#!/usr/bin/env python3
"""
build_dashboard.py — gera dashboard/index.html a partir do whoop_data.json.

    python3 build_dashboard.py

Regras que este gerador segue, por decisão de projeto:
  * Nenhum placeholder. Um card só aparece se os campos que ele usa existirem
    no seu whoop_data.json. Campos vazios viram uma nota, não um número falso.
  * Toda conta feita aqui tem a fórmula impressa na própria página.
  * Toda suposição é um controle ajustável, não uma constante escondida.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "whoop_data.json"
WEIGHT_FILE = ROOT / "whoop_weight.json"
OUT_FILE = ROOT / "dashboard" / "index.html"
ORB_FILE = ROOT / "dashboard" / "orb-reference.html"

MS_PER_HOUR = 3_600_000


def read_weight_log() -> list:
    if not WEIGHT_FILE.exists():
        return []
    try:
        return json.loads(WEIGHT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


# --------------------------------------------------------------------------- #
# Transformação: whoop_data.json -> série diária
# --------------------------------------------------------------------------- #

def day_of(stamp: str | None) -> str | None:
    return stamp[:10] if stamp else None


def minutes_between(start: str | None, end: str | None) -> float | None:
    if not (start and end):
        return None
    try:
        parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        return round((parse(end) - parse(start)).total_seconds() / 60, 1)
    except ValueError:
        return None


def build_series(data: dict) -> list[dict]:
    """Uma linha por dia, com os nomes de campo reais do WHOOP preservados."""
    days: dict[str, dict] = {}

    def slot(date: str) -> dict:
        return days.setdefault(date, {"date": date})

    cycle_day: dict = {}
    for cycle in data.get("cycles") or []:
        date = day_of(cycle.get("start"))
        if not date:
            continue
        cycle_day[cycle.get("id")] = date
        score = cycle.get("score") or {}
        entry = slot(date)
        entry["strain"] = score.get("strain")
        entry["kilojoule"] = score.get("kilojoule")
        entry["cycle_average_heart_rate"] = score.get("average_heart_rate")
        entry["cycle_max_heart_rate"] = score.get("max_heart_rate")

    for recovery in data.get("recovery") or []:
        date = cycle_day.get(recovery.get("cycle_id")) or day_of(
            recovery.get("created_at"))
        if not date:
            continue
        score = recovery.get("score") or {}
        entry = slot(date)
        entry["recovery_score"] = score.get("recovery_score")
        entry["hrv_rmssd_milli"] = score.get("hrv_rmssd_milli")
        entry["resting_heart_rate"] = score.get("resting_heart_rate")
        entry["spo2_percentage"] = score.get("spo2_percentage")
        entry["skin_temp_celsius"] = score.get("skin_temp_celsius")
        entry["user_calibrating"] = score.get("user_calibrating")

    for sleep in data.get("sleep") or []:
        if sleep.get("nap"):
            continue  # cochilos não entram na noite principal
        date = day_of(sleep.get("end") or sleep.get("start"))
        if not date:
            continue
        score = sleep.get("score") or {}
        stages = score.get("stage_summary") or {}
        needed = score.get("sleep_needed") or {}
        entry = slot(date)
        in_bed = stages.get("total_in_bed_time_milli")
        awake = stages.get("total_awake_time_milli")
        if in_bed is not None and awake is not None:
            entry["asleep_hours"] = round((in_bed - awake) / MS_PER_HOUR, 3)
            entry["in_bed_hours"] = round(in_bed / MS_PER_HOUR, 3)
        entry["rem_hours"] = _hours(stages.get("total_rem_sleep_time_milli"))
        entry["sws_hours"] = _hours(stages.get("total_slow_wave_sleep_time_milli"))
        entry["light_hours"] = _hours(stages.get("total_light_sleep_time_milli"))
        entry["disturbance_count"] = stages.get("disturbance_count")
        entry["sleep_performance_percentage"] = score.get(
            "sleep_performance_percentage")
        entry["sleep_efficiency_percentage"] = score.get(
            "sleep_efficiency_percentage")
        entry["sleep_consistency_percentage"] = score.get(
            "sleep_consistency_percentage")
        entry["respiratory_rate"] = score.get("respiratory_rate")
        if needed:
            total = sum(v for v in needed.values() if isinstance(v, (int, float)))
            entry["sleep_needed_hours"] = round(total / MS_PER_HOUR, 3)
            entry["need_baseline_hours"] = _hours(needed.get("baseline_milli"))
            entry["need_debt_hours"] = _hours(
                needed.get("need_from_sleep_debt_milli"))
            entry["need_strain_hours"] = _hours(
                needed.get("need_from_recent_strain_milli"))

    for workout in data.get("workouts") or []:
        date = day_of(workout.get("start"))
        if not date:
            continue
        score = workout.get("score") or {}
        entry = slot(date)
        entry.setdefault("workouts", [])
        entry["workouts"].append({
            "sport_name": workout.get("sport_name") or workout.get("sport_id"),
            "strain": score.get("strain"),
            "duration_min": minutes_between(workout.get("start"), workout.get("end")),
            "average_heart_rate": score.get("average_heart_rate"),
            "max_heart_rate": score.get("max_heart_rate"),
            "distance_meter": score.get("distance_meter"),
            "kilojoule": score.get("kilojoule"),
        })

    return [days[date] for date in sorted(days)]


def _hours(milli) -> float | None:
    return round(milli / MS_PER_HOUR, 3) if isinstance(milli, (int, float)) else None


def coverage_report(series: list[dict]) -> dict:
    """Quantos dias têm cada campo preenchido — alimenta a seção de qualidade."""
    fields = [
        "recovery_score", "hrv_rmssd_milli", "resting_heart_rate",
        "spo2_percentage", "skin_temp_celsius", "strain", "kilojoule",
        "asleep_hours", "sleep_needed_hours", "sleep_performance_percentage",
        "sleep_efficiency_percentage", "sleep_consistency_percentage",
        "respiratory_rate", "rem_hours", "sws_hours", "disturbance_count",
    ]
    total = len(series)
    return {
        "total_days": total,
        "fields": {
            field: sum(1 for day in series if day.get(field) is not None)
            for field in fields
        },
    }


def extract_orb() -> dict:
    """Lê o orbe de referência e devolve suas três partes, sem reescrevê-lo."""
    if not ORB_FILE.exists():
        return {}
    raw = ORB_FILE.read_text(encoding="utf-8")
    def between(open_tag: str, close_tag: str) -> str:
        try:
            start = raw.index(open_tag) + len(open_tag)
            return raw[start:raw.index(close_tag, start)]
        except ValueError:
            return ""
    js = between("<script>", "</script>")
    # Duas linhas cirúrgicas, para a cor seguir o valor exibido sem reescrever
    # o resto do orbe: ORB_COLOR deixa de ser constante e passa a ser lido a
    # cada quadro. Ordenação por profundidade, curva de opacidade e respiração
    # continuam exatamente como no original.
    js = js.replace(
        "  const ORB_COLOR = [40, 224, 123];          // r,g,b -- drive this from the value",
        "  // ORB_COLOR vem de window.ORB_COLOR, lido a cada quadro (ver frame)")
    js = js.replace("  const [cr, cg, cb] = ORB_COLOR;\n  let t = 0;", "  let t = 0;")
    js = js.replace(
        "  (function frame(){\n    if (!W) size();",
        "  (function frame(){\n    if (!W) size();\n"
        "    const [cr, cg, cb] = window.ORB_COLOR || [40, 224, 123];")
    return {"css": between("<style>", "</style>"), "js": js}


# --------------------------------------------------------------------------- #
# Geração
# --------------------------------------------------------------------------- #

BANNER = (
    '<div class="demo-banner"><b>Demonstração.</b> Estes números são sintéticos, '
    'gerados por tests/mock_whoop.py só para você ver o layout. Nada aqui é seu. '
    'O seu dashboard de verdade sai em dashboard/index.html depois do '
    '<span class="mono">python3 whoop.py fetch</span>.</div>')


def demo_data() -> dict:
    """Histórico sintético do servidor de teste, para pré-visualizar o layout."""
    sys.path.insert(0, str(ROOT / "tests"))
    import mock_whoop  # noqa: PLC0415

    history = mock_whoop.build_history()
    return {
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cycles": history["cycle"],
        "recovery": history["recovery"],
        "sleep": history["activity/sleep"],
        "workouts": history["activity/workout"],
        "profile": {}, "errors": {},
        "weight_log": [{"date": f"2026-0{3 + i // 4}-{1 + (i % 4) * 7:02d}",
                        "weight_kilogram": round(84 - i * 0.35, 1),
                        "source": "demo"} for i in range(12)],
        "body_measurement": {"height_meter": 1.78, "weight_kilogram": 76.4,
                             "max_heart_rate": 191},
        "counts": {k: len(v) for k, v in history.items()},
    }


def titulo_pedido() -> str | None:
    """Lê --titulo "Meu nome" da linha de comando."""
    if "--titulo" in sys.argv:
        i = sys.argv.index("--titulo")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main() -> int:
    demo = "--demo" in sys.argv
    if demo:
        data = demo_data()
    elif not DATA_FILE.exists():
        print(f"ERRO: {DATA_FILE.name} não existe. Rode antes:\n"
              f"  python3 whoop.py fetch\n"
              f"Para só ver o layout com dados falsos:\n"
              f"  python3 build_dashboard.py --demo", file=sys.stderr)
        return 1
    else:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    series = build_series(data)
    if not series:
        print("ERRO: nenhum dia encontrado no whoop_data.json.", file=sys.stderr)
        return 1

    body = data.get("body_measurement") or {}
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fetched_at": data.get("fetched_at"),
        "series": series,
        "coverage": coverage_report(series),
        "body_measurement": {
            "height_meter": body.get("height_meter"),
            "weight_kilogram": body.get("weight_kilogram"),
            "max_heart_rate": body.get("max_heart_rate"),
        },
        "weight_log": data.get("weight_log") or read_weight_log(),
        "counts": data.get("counts") or {},
        "errors": data.get("errors") or {},
    }

    template = (ROOT / "dashboard" / "template.html").read_text(encoding="utf-8")
    orb = extract_orb()
    html = (template
            .replace("/*__ORB_CSS__*/", orb.get("css", ""))
            .replace("/*__ORB_JS__*/", orb.get("js", ""))
            .replace("<!--__BANNER__-->", BANNER if demo else "")
            .replace("<title>__TITULO__</title>",
                     f"<title>{titulo_pedido() or 'Painel WHOOP'}</title>")
            .replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False)))

    out = OUT_FILE.with_name("demo.html") if demo else OUT_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    label = "Demonstração gerada" if demo else "Dashboard gerado"
    print(f"{label}: {out}  ({size_kb} KB, {len(series)} dias)")
    print(f"Abra com: xdg-open {out}   (ou clique duas vezes no arquivo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
