"""
fase4_seleccion.py — Selección de los 10 conjuntos de pesos por horizonte
(sección 7, Fase 4), a partir de resultados/simulaciones.csv.

JERARQUÍA REEMPLAZADA el 2026-10-19 (ver INSTRUCCIONES.md sección 3):
  P0 = validez (valida_P0=True). Único filtro binario; todo lo que pasa P0
       es "factible" (ya no hay restricción dura de oscilación <10V como P1
       separado).
  P1 = minimizar desv_media_max (|media(v_cap) - 150V|, peor de los 6).
  P2 = minimizar osc_max (oscilación pico-pico de v_cap/Osc.Cap, peor de los
       6) — objetivo principal.
  P3 = desempate en cascada: |idc_media| lo más cercano a 0, luego idc_osc
       (oscilación de I.DC) lo menor posible.
  Empates en P1 y P2 se evalúan con tolerancia TOL_EMPATE (relativa) antes de
  pasar al siguiente nivel.

i_circ es informativo únicamente, no interviene en el ordenamiento.

Prueba 1 = caso base (fase=fase1), aunque no pase P0 (se marca).
Pruebas 2-10 = los 9 mejores candidatos que pasan P0, ordenados por la
jerarquía de arriba, elegidos de forma VORAZ exigiendo diversidad: cada
candidato nuevo debe diferir del caso base Y de cada ya seleccionado en al
menos un peso por una distancia en log10 >= DIST_MIN_LOG10 (factor >=2).
Si no hay 9 diversos que pasen P0, se completa con los que SÍ pasan P0 más
cercanos al mejor P2 ya seleccionado (sin relajar P0), marcados "NO DIVERSO".

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


def _empatados(a: float, b: float) -> bool:
    """True si a y b están dentro de TOL_EMPATE (relativa a b)."""
    if a == b:
        return True
    if b == 0:
        return False
    return abs(a - b) / abs(b) < config.TOL_EMPATE


def _comparar(a: dict, b: dict) -> int:
    """Comparador lexicográfico estricto de la nueva jerarquía (sección 3):
    P1 (desv_media_max) -> si empatan, P2 (osc_max) -> si empatan, P3
    (|idc_media|, luego idc_osc). Devuelve <0 si a es mejor, >0 si b es mejor."""
    p1_a = _to_float(a, "desv_media_max", float("inf"))
    p1_b = _to_float(b, "desv_media_max", float("inf"))
    if not _empatados(p1_a, p1_b):
        return -1 if p1_a < p1_b else 1

    p2_a = _to_float(a, "osc_max", float("inf"))
    p2_b = _to_float(b, "osc_max", float("inf"))
    if not _empatados(p2_a, p2_b):
        return -1 if p2_a < p2_b else 1

    idc_media_a = abs(_to_float(a, "idc_media", float("inf")))
    idc_media_b = abs(_to_float(b, "idc_media", float("inf")))
    if idc_media_a != idc_media_b:
        return -1 if idc_media_a < idc_media_b else 1

    idc_osc_a = _to_float(a, "idc_osc", float("inf"))
    idc_osc_b = _to_float(b, "idc_osc", float("inf"))
    if idc_osc_a != idc_osc_b:
        return -1 if idc_osc_a < idc_osc_b else 1

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

    factibles = [r for r in filas_h if _es_true(r, "valida_P0")]
    factibles.sort(key=functools.cmp_to_key(_comparar))

    seleccionados = []
    for candidato in factibles:
        if caso_base.get("id") == candidato.get("id"):
            continue
        if _es_diverso(candidato, seleccionados, caso_base):
            seleccionados.append(candidato)
        if len(seleccionados) == 9:
            break

    no_diverso_marcados = []
    if len(seleccionados) < 9:
        # No hay 9 diversos que pasen P0: completar con los mejores factibles
        # restantes (aunque no diversos), marcados NO DIVERSO. P0 nunca se
        # relaja; solo se relaja la exigencia de diversidad.
        faltan = 9 - len(seleccionados)
        ids_usados = {s.get("id") for s in seleccionados} | {caso_base.get("id")}
        candidatos_relleno = [r for r in factibles if r.get("id") not in ids_usados]
        for r in candidatos_relleno[:faltan]:
            seleccionados.append(r)
            no_diverso_marcados.append(r.get("id"))

    bloque = {
        "horizonte": horizonte,
        "prueba_1_caso_base": caso_base,
        "pruebas_2_a_10": seleccionados,
        "no_cumple_ids": no_diverso_marcados,  # mantiene el nombre de clave por compatibilidad con Fase 5/6
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
              f"factibles (P0): {bloque['n_factibles']}")
        print(f"  Prueba 1 (caso base): id={bloque['prueba_1_caso_base']['id']}  "
              f"estado={bloque['prueba_1_caso_base']['estado']}")
        for i, r in enumerate(bloque["pruebas_2_a_10"], start=2):
            marca = " [NO DIVERSO]" if r["id"] in bloque["no_cumple_ids"] else ""
            print(f"  Prueba {i}: id={r['id']}  desv_media_max={r.get('desv_media_max')}  "
                  f"osc_max={r.get('osc_max')}{marca}")

        if len(bloque["pruebas_2_a_10"]) < 9:
            print(f"  ADVERTENCIA: solo se encontraron {len(bloque['pruebas_2_a_10'])} de 9 "
                  f"conjuntos factibles para las Pruebas 2-10.")

        resultado[str(h)] = bloque

    out_path = config.RESULTADOS_DIR / "fase4_seleccion.json"
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\nSelección guardada en {out_path}")
    print("Fase 4 completa.")


if __name__ == "__main__":
    main()
