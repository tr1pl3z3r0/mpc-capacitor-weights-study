"""
fase4_seleccion.py — Selección de los 10 conjuntos de pesos por horizonte
(sección 7, Fase 4), a partir de resultados/simulaciones.csv.

Prueba 1 = caso base (fase=fase1), aunque no cumpla P0/P1 (se marca).
Pruebas 2-10 = los 9 mejores candidatos que:
  - cumplen P0 y P1 (valida_P0=True, cumple_P1=True);
  - ordenados por la jerarquía lexicográfica estricta de la sección 3
    (P2: rms_icirc_peor: luego P3 si |diff|<TOL_EMPATE: pico_abs_icirc, luego
    rmse_vcap; luego P4: margen 10-osc, luego itae, luego duracion_s);
  - elegidos de forma VORAZ exigiendo diversidad: cada candidato nuevo debe
    diferir del caso base Y de cada ya seleccionado en al menos un peso por
    una distancia en log10 >= DIST_MIN_LOG10 (factor >=2).
Si no hay 9 diversos, se completa con los válidos más cercanos a OSC_MAX,
marcados "NO CUMPLE" (la restricción de 10V NUNCA se relaja: estos puntos ya
incumplieron P1, se incluyen solo para llenar la tabla, no se consideran
factibles).

Uso:
    python fase4_seleccion.py
"""

import csv
import functools
import json
import math

import config

NOMBRES_PESOS = config.NOMBRES_PESOS


def _leer_csv() -> list:
    if not config.CSV_SIMULACIONES.exists():
        raise RuntimeError(f"No existe {config.CSV_SIMULACIONES}; correr las Fases 1-3 primero.")
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_float(row: dict, key: str, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _es_true(row: dict, key: str) -> bool:
    return row.get(key) in ("True", "true", True)


def _distancia_log10(row_a: dict, row_b: dict) -> float:
    """Distancia máxima en log10 entre dos filas, sobre los 7 pesos."""
    dist_max = 0.0
    for peso in NOMBRES_PESOS:
        va = _to_float(row_a, peso)
        vb = _to_float(row_b, peso)
        if va is None or vb is None or va <= 0 or vb <= 0:
            continue
        d = abs(math.log10(va) - math.log10(vb))
        dist_max = max(dist_max, d)
    return dist_max


def _es_diverso(candidato: dict, seleccionados: list, caso_base: dict) -> bool:
    referencias = [caso_base] + seleccionados
    return all(_distancia_log10(candidato, ref) >= config.DIST_MIN_LOG10 for ref in referencias)


def _criterios_p4(row: dict):
    osc_max = _to_float(row, "osc_max", float("inf"))
    margen = config.OSC_MAX - osc_max if osc_max != float("inf") else float("-inf")
    itae = _to_float(row, "itae", float("inf"))
    duracion = _to_float(row, "duracion_s", float("inf"))
    return (-margen, itae, duracion)


def _comparar(a: dict, b: dict) -> int:
    """Comparador lexicográfico estricto de la sección 3: P2 (rms_icirc_peor);
    si |diff relativa| < TOL_EMPATE se consideran empatados en P2 y se pasa a
    P3 (pico_abs_icirc, luego rmse_vcap); si P3 también empata exactamente, P4
    (margen, itae, duracion). Devuelve <0 si a es mejor, >0 si b es mejor."""
    rms_a = _to_float(a, "rms_icirc_peor", float("inf"))
    rms_b = _to_float(b, "rms_icirc_peor", float("inf"))

    diff_relativa = None
    if rms_a not in (float("inf"),) and rms_b not in (float("inf"),) and rms_b != 0:
        diff_relativa = abs(rms_a - rms_b) / abs(rms_b)

    if diff_relativa is None or diff_relativa >= config.TOL_EMPATE:
        if rms_a != rms_b:
            return -1 if rms_a < rms_b else 1
        # rms exactamente iguales (p.ej. ambos inf): caer a P3 igual.

    pico_a = _to_float(a, "pico_abs_icirc", float("inf"))
    pico_b = _to_float(b, "pico_abs_icirc", float("inf"))
    if pico_a != pico_b:
        return -1 if pico_a < pico_b else 1

    rmse_a = _to_float(a, "rmse_vcap", float("inf"))
    rmse_b = _to_float(b, "rmse_vcap", float("inf"))
    if rmse_a != rmse_b:
        return -1 if rmse_a < rmse_b else 1

    p4_a = _criterios_p4(a)
    p4_b = _criterios_p4(b)
    if p4_a != p4_b:
        return -1 if p4_a < p4_b else 1

    return 0


def seleccionar_horizonte(filas: list, horizonte: int) -> dict:
    filas_h = [r for r in filas if int(r["horizonte"]) == horizonte]

    caso_base_candidatos = [r for r in filas_h if r["fase"] == "fase1"]
    if not caso_base_candidatos:
        # Fallback: buscar una fila con pesos == PESOS_BASE en cualquier fase.
        caso_base_candidatos = [
            r for r in filas_h
            if all(abs(_to_float(r, p, -1) - config.PESOS_BASE[p]) < 1e-9 for p in NOMBRES_PESOS)
        ]
    if not caso_base_candidatos:
        raise RuntimeError(f"No se encontró el caso base para horizonte {horizonte}. "
                            f"Correr fase1_caso_base.py primero.")
    caso_base = caso_base_candidatos[0]

    factibles = [r for r in filas_h if _es_true(r, "valida_P0") and _es_true(r, "cumple_P1")]
    factibles.sort(key=functools.cmp_to_key(_comparar))

    seleccionados = []
    for candidato in factibles:
        if caso_base.get("id") == candidato.get("id"):
            continue
        if _es_diverso(candidato, seleccionados, caso_base):
            seleccionados.append(candidato)
        if len(seleccionados) == 9:
            break

    no_cumple_marcados = []
    if len(seleccionados) < 9:
        # Completar con los válidos (P0, aunque no P1) más cercanos a OSC_MAX,
        # sin relajar la restricción: se marcan NO CUMPLE y no se consideran
        # factibles. "Válidos" = pasan P0 aunque no P1.
        faltan = 9 - len(seleccionados)
        candidatos_relleno = [
            r for r in filas_h
            if _es_true(r, "valida_P0") and not _es_true(r, "cumple_P1")
            and r.get("id") not in {s.get("id") for s in seleccionados}
            and r.get("id") != caso_base.get("id")
        ]
        candidatos_relleno.sort(key=lambda r: abs(_to_float(r, "osc_max", float("inf")) - config.OSC_MAX))
        for r in candidatos_relleno[:faltan]:
            seleccionados.append(r)
            no_cumple_marcados.append(r.get("id"))

    bloque = {
        "horizonte": horizonte,
        "prueba_1_caso_base": caso_base,
        "pruebas_2_a_10": seleccionados,
        "no_cumple_ids": no_cumple_marcados,
        "n_simulaciones": len(filas_h),
        "n_factibles": len(factibles),
    }
    return bloque


def main():
    filas = _leer_csv()
    resultado = {}

    print("=" * 60)
    print("  Fase 4: selección de los 10 conjuntos por horizonte")
    print("=" * 60)

    for h in config.HORIZONTES:
        print(f"\n[Horizonte N={h}]")
        try:
            bloque = seleccionar_horizonte(filas, h)
        except RuntimeError as e:
            print(f"  ERROR: {e}")
            continue

        print(f"  simulaciones totales: {bloque['n_simulaciones']}  "
              f"factibles (P0+P1): {bloque['n_factibles']}")
        print(f"  Prueba 1 (caso base): id={bloque['prueba_1_caso_base']['id']}  "
              f"estado={bloque['prueba_1_caso_base']['estado']}")
        for i, r in enumerate(bloque["pruebas_2_a_10"], start=2):
            marca = " [NO CUMPLE]" if r["id"] in bloque["no_cumple_ids"] else ""
            print(f"  Prueba {i}: id={r['id']}  rms_icirc_peor={r.get('rms_icirc_peor')}  "
                  f"osc_max={r.get('osc_max')}{marca}")

        if len(bloque["pruebas_2_a_10"]) < 9:
            print(f"  ADVERTENCIA: solo se encontraron {len(bloque['pruebas_2_a_10'])} de 9 "
                  f"conjuntos para las Pruebas 2-10 (incluso tras completar con NO CUMPLE).")

        resultado[str(h)] = bloque

    out_path = config.RESULTADOS_DIR / "fase4_seleccion.json"
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\nSelección guardada en {out_path}")
    print("Fase 4 completa.")


if __name__ == "__main__":
    main()
