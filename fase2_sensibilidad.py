"""
fase2_sensibilidad.py — Sensibilidad un peso a la vez, en HORIZONTE_REFERENCIA
(sección 7, Fase 2). Para cada peso, prueba base x 10^(-3..+3) manteniendo los
demás en su valor base. Genera figuras de osc/RMS/pico vs peso (log) y registra
qué pesos se pueden fijar (cambio < 2% en todo el rango) o acotar (rango con
fallas/invalidez).

Uso:
    python fase2_sensibilidad.py            # solo esta máquina, sin coordinar
    python fase2_sensibilidad.py --git       # coordina con otras máquinas vía GitHub
"""

import json
import sys

import numpy as np

import config
from simulador import simular_punto

EXPONENTES = [-3, -2, -1, 0, 1, 2, 3]

# PESOS_IGUALES (q11=q22, q44=q55): solo se barre el peso independiente de
# cada par; el dependiente se deriva igual. Evita romper la restricción de
# igualdad durante el barrido de sensibilidad.
_PESOS_DEPENDIENTES = {b for _, b in config.PESOS_IGUALES}
PESOS_A_BARRER = [p for p in config.NOMBRES_PESOS if p not in _PESOS_DEPENDIENTES]


def _expandir_pesos_iguales(pesos: dict) -> dict:
    pesos = dict(pesos)
    for independiente, dependiente in config.PESOS_IGUALES:
        pesos[dependiente] = pesos[independiente]
    return pesos


def main():
    usar_git = "--git" in sys.argv

    print("=" * 60)
    print(f"  Fase 2: sensibilidad un peso a la vez (N={config.HORIZONTE_REFERENCIA}, "
          f"maquina={config.MAQUINA_ID}, git={usar_git})")
    print(f"  Pesos a barrer: {PESOS_A_BARRER} (q22=q11 y q55=q44 se derivan automáticamente)")
    print("=" * 60)

    resultados = {}  # peso -> lista de (exponente, fila)

    for peso in PESOS_A_BARRER:
        print(f"\n--- Peso: {peso} ---")
        resultados[peso] = []
        for exp in EXPONENTES:
            pesos_punto = dict(config.PESOS_BASE)
            pesos_punto[peso] = config.PESOS_BASE[peso] * (10.0 ** exp)
            pesos_punto = _expandir_pesos_iguales(pesos_punto)

            fila = simular_punto(horizonte=config.HORIZONTE_REFERENCIA, pesos=pesos_punto,
                                  fase="fase2", usar_git=usar_git)
            if fila is None:
                print(f"  {peso}*10^{exp:+d} = {pesos_punto[peso]:.4g}  "
                      f"(ya tomado/terminado por otra máquina, se omite)")
                continue
            resultados[peso].append((exp, fila))
            print(f"  {peso}*10^{exp:+d} = {pesos_punto[peso]:.4g}  "
                  f"estado={fila['estado']}  osc_max={fila.get('osc_max','')}  "
                  f"desv_media_max={fila.get('desv_media_max','')}")

    # Análisis: fijar pesos con variación < 2%, o acotar rango si hay fallas.
    conclusiones = {}
    for peso, puntos in resultados.items():
        validos = [(exp, f) for exp, f in puntos if f["estado"] == "OK"]
        if len(validos) < 2:
            conclusiones[peso] = {
                "accion": "INSUFICIENTES_DATOS_VALIDOS",
                "n_validos": len(validos),
                "nota": "Menos de 2 puntos válidos (OK) en el barrido; no se puede evaluar sensibilidad.",
            }
            continue

        oscs = [float(f["osc_max"]) for _, f in validos]  # P2: objetivo principal
        desvs = [float(f["desv_media_max"]) for _, f in validos]  # P1

        def variacion_pct(vals):
            vals = np.array(vals)
            if vals.min() == 0:
                return float("inf")
            return float((vals.max() - vals.min()) / abs(vals.min()) * 100)

        var_osc = variacion_pct(oscs)
        var_desv = variacion_pct(desvs)

        exps_validos = [exp for exp, _ in validos]
        rango_recortado = (min(exps_validos), max(exps_validos)) != (min(EXPONENTES), max(EXPONENTES))

        if var_osc < 2 and var_desv < 2:
            conclusiones[peso] = {
                "accion": "FIJAR_EN_BASE",
                "var_osc_pct": round(var_osc, 3),
                "var_desv_media_pct": round(var_desv, 3),
                "nota": f"Variación <2% en todo el rango válido; fijar {peso} en su valor base "
                        f"y excluirlo de la optimización.",
            }
        else:
            conclusiones[peso] = {
                "accion": "OPTIMIZAR",
                "var_osc_pct": round(var_osc, 3),
                "var_desv_media_pct": round(var_desv, 3),
                "rango_valido_log10": rango_recortado and [min(exps_validos), max(exps_validos)] or None,
                "nota": "Variación significativa; mantener en la optimización."
                        + (" Rango recortado por fallas/invalidez fuera de este intervalo."
                           if rango_recortado else ""),
            }

    print("\n" + "=" * 60)
    print("  Conclusiones de sensibilidad")
    print("=" * 60)
    for peso, c in conclusiones.items():
        print(f"  {peso}: {c['accion']} — {c['nota']}")

    out_path = config.RESULTADOS_DIR / "fase2_conclusiones.json"
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(conclusiones, f, indent=2, ensure_ascii=False)
    print(f"\nConclusiones guardadas en {out_path}")
    print("Fase 2 completa. Ver resultados/simulaciones.csv (fase=fase2) para los datos crudos.")
    print("Las figuras de sensibilidad se generan en la Fase 5 (graficar_fase2.py), a partir de este CSV.")


if __name__ == "__main__":
    main()
