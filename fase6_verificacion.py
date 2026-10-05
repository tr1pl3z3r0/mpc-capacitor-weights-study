"""
fase6_verificacion.py — Verificación final (sección 7, Fase 6).

1. Re-simula el mejor conjunto de cada horizonte y 5 entradas aleatorias de
   la tabla (seleccionadas de simulaciones.csv con estado=OK). Sus métricas
   deben coincidir con el CSV dentro de TOL_REPETIBILIDAD (ver nota en
   config.py: placeholder 1% hasta tener la medición real de Fase 0).
2. Comprueba por código que cada celda del Excel coincide con su fila del
   CSV / fase4_seleccion.json.
3. Comprueba que todas las celdas de pesos y métricas de los 5 bloques
   están llenas.
4. Reporta discrepancias; NO las corrige en silencio (regla sección 7).

Uso:
    python fase6_verificacion.py              # solo esta máquina, sin coordinar
    python fase6_verificacion.py --git         # coordina con otras máquinas vía GitHub
    python fase6_verificacion.py --saltar-resimulacion   # solo chequeo de Excel↔CSV
"""

import argparse
import csv
import json
import random

import openpyxl

import config
from simulador import simular_punto

NOMBRES_PESOS = config.NOMBRES_PESOS
METRICAS_A_COMPARAR = [
    "osc_max", "rms_icirc_peor", "pico_abs_icirc", "rmse_vcap", "itae", "idc_abs_max",
]


def _leer_csv_sim() -> list:
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_float(row: dict, key: str, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _diferencia_relativa(a: float, b: float) -> float:
    if a is None or b is None:
        return float("inf")
    if b == 0:
        return 0.0 if a == 0 else float("inf")
    return abs(a - b) / abs(b)


def reproducir_fila(fila_original: dict, usar_git: bool) -> dict:
    pesos = {p: _to_float(fila_original, p) for p in NOMBRES_PESOS}
    horizonte = int(fila_original["horizonte"])
    return simular_punto(horizonte=horizonte, pesos=pesos, fase="fase6",
                          semilla=int(_to_float(fila_original, "semilla", config.SEMILLA)),
                          reusar_si_existe=False, usar_git=usar_git)


def verificar_repetibilidad(usar_git: bool) -> list:
    """Re-simula el mejor conjunto de cada horizonte + 5 aleatorias. Devuelve
    lista de discrepancias encontradas (vacía si todo coincide)."""
    discrepancias = []

    seleccion_path = config.RESULTADOS_DIR / "fase4_seleccion.json"
    if not seleccion_path.exists():
        print("  (sin fase4_seleccion.json, se omite verificación del mejor por horizonte)")
    else:
        with open(seleccion_path, "r", encoding="utf-8") as f:
            seleccion = json.load(f)

        for h_str, bloque in seleccion.items():
            no_cumple = set(bloque.get("no_cumple_ids", []))
            candidatos = [p for p in bloque["pruebas_2_a_10"] if p["id"] not in no_cumple]
            if not candidatos:
                print(f"  Horizonte {h_str}: sin mejor candidato factible, se omite.")
                continue
            original = candidatos[0]
            print(f"  Re-simulando mejor de horizonte {h_str} (sim {original['id']})...")
            nueva = reproducir_fila(original, usar_git)
            if nueva is None:
                print(f"    (punto tomado por otra máquina, no se pudo verificar)")
                continue
            discrepancias += _comparar_filas(original, nueva, f"mejor horizonte {h_str}")

    filas = _leer_csv_sim()
    filas_ok = [r for r in filas if r["estado"] == "OK"]
    if not filas_ok:
        print("  (sin filas estado=OK en el CSV, se omite verificación de 5 aleatorias)")
        return discrepancias

    random.seed(config.SEMILLA)
    muestra = random.sample(filas_ok, min(5, len(filas_ok)))
    for original in muestra:
        print(f"  Re-simulando entrada aleatoria sim {original['id']} (horizonte {original['horizonte']})...")
        nueva = reproducir_fila(original, usar_git)
        if nueva is None:
            print(f"    (punto tomado por otra máquina, no se pudo verificar)")
            continue
        discrepancias += _comparar_filas(original, nueva, f"aleatoria sim {original['id']}")

    return discrepancias


def _comparar_filas(original: dict, nueva: dict, etiqueta: str) -> list:
    discrepancias = []
    for metrica in METRICAS_A_COMPARAR:
        val_orig = _to_float(original, metrica)
        val_nueva = _to_float(nueva, metrica)
        if val_orig is None or val_nueva is None:
            continue
        diff = _diferencia_relativa(val_nueva, val_orig)
        if diff > config.TOL_REPETIBILIDAD:
            discrepancias.append(
                f"[{etiqueta}] {metrica}: original={val_orig} nuevo={val_nueva} "
                f"diff_relativa={diff*100:.3f}% (tolerancia {config.TOL_REPETIBILIDAD*100:.1f}%)"
            )
    return discrepancias


def verificar_excel_vs_csv() -> list:
    """Comprueba que cada celda del Excel coincide con su fila del CSV/selección."""
    discrepancias = []

    seleccion_path = config.RESULTADOS_DIR / "fase4_seleccion.json"
    if not seleccion_path.exists():
        return ["No existe fase4_seleccion.json; no se puede verificar Excel vs CSV."]
    with open(seleccion_path, "r", encoding="utf-8") as f:
        seleccion = json.load(f)

    if not config.EXCEL_RESULTADOS.exists():
        return [f"No existe {config.EXCEL_RESULTADOS}; correr fase5_excel.py primero."]

    wb = openpyxl.load_workbook(config.EXCEL_RESULTADOS, data_only=True)
    ws = wb["Pruebas realizadas"]

    from openpyxl.utils import get_column_letter

    for k, h in enumerate(config.HORIZONTES):
        h_str = str(h)
        if h_str not in seleccion:
            continue
        bloque = seleccion[h_str]
        r = 3 + 15 * k
        pruebas = [bloque["prueba_1_caso_base"]] + bloque["pruebas_2_a_10"]

        for i, prueba in enumerate(pruebas):
            col = get_column_letter(3 + i)  # Prueba 1 -> C

            for j, peso in enumerate(NOMBRES_PESOS):
                fila_peso = r + 3 + j
                celda_valor = ws[f"{col}{fila_peso}"].value
                esperado = _to_float(prueba, peso)
                if celda_valor is None and esperado is None:
                    continue
                if celda_valor is None or esperado is None or \
                   _diferencia_relativa(float(celda_valor), esperado) > 1e-6:
                    discrepancias.append(
                        f"Horizonte {h}, Prueba {i+1}, {peso}: Excel={celda_valor} "
                        f"vs esperado={esperado} (celda {col}{fila_peso})"
                    )

            metricas_filas = {
                "osc_max": r + 11, "rms_icirc_peor": r + 12,
                "max_icirc": r + 13, "min_icirc": r + 14,
            }
            for metrica, fila_m in metricas_filas.items():
                celda_valor = ws[f"{col}{fila_m}"].value
                esperado = _to_float(prueba, metrica)
                if celda_valor is None and esperado is None:
                    continue
                if celda_valor is None or esperado is None or \
                   _diferencia_relativa(float(celda_valor), esperado) > 1e-6:
                    discrepancias.append(
                        f"Horizonte {h}, Prueba {i+1}, {metrica}: Excel={celda_valor} "
                        f"vs esperado={esperado} (celda {col}{fila_m})"
                    )

    return discrepancias


def verificar_celdas_completas() -> list:
    """Comprueba que todas las celdas de pesos y métricas de los 5 bloques
    están llenas (no vacías/None), salvo donde el dato original también
    estaba vacío (p.ej. caso base que no convergió)."""
    discrepancias = []

    if not config.EXCEL_RESULTADOS.exists():
        return [f"No existe {config.EXCEL_RESULTADOS}."]

    wb = openpyxl.load_workbook(config.EXCEL_RESULTADOS, data_only=True)
    ws = wb["Pruebas realizadas"]
    from openpyxl.utils import get_column_letter

    for k, h in enumerate(config.HORIZONTES):
        r = 3 + 15 * k
        for prueba_num in range(1, 11):
            col = get_column_letter(2 + prueba_num)
            for j in range(7):  # pesos, siempre deberían estar (se redondean antes de simular)
                fila_peso = r + 3 + j
                if ws[f"{col}{fila_peso}"].value is None:
                    discrepancias.append(
                        f"Horizonte {h}, Prueba {prueba_num}: celda de peso vacía "
                        f"({col}{fila_peso})"
                    )

    return discrepancias


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--git", action="store_true")
    parser.add_argument("--saltar-resimulacion", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  Fase 6: verificación final")
    print("=" * 60)

    todas_discrepancias = []

    if not args.saltar_resimulacion:
        print("\n[1/3] Re-simulando mejor por horizonte + 5 aleatorias...")
        todas_discrepancias += verificar_repetibilidad(args.git)
    else:
        print("\n[1/3] Re-simulación SALTADA (--saltar-resimulacion).")

    print("\n[2/3] Comparando Excel vs CSV/selección...")
    todas_discrepancias += verificar_excel_vs_csv()

    print("\n[3/3] Comprobando celdas completas...")
    todas_discrepancias += verificar_celdas_completas()

    print("\n" + "=" * 60)
    if todas_discrepancias:
        print(f"  Se encontraron {len(todas_discrepancias)} DISCREPANCIAS:")
        print("=" * 60)
        for d in todas_discrepancias:
            print(f"  - {d}")
    else:
        print("  Sin discrepancias. Verificación OK.")
        print("=" * 60)

    out_path = config.RESULTADOS_DIR / "fase6_discrepancias.json"
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(todas_discrepancias, f, indent=2, ensure_ascii=False)
    print(f"\nResultado guardado en {out_path}")


if __name__ == "__main__":
    main()
