"""
fase5_informe.py — Genera resultados/informe.md (sección 7, Fase 5), en español.

Incluye: configuración usada, definiciones de métricas y su justificación,
resultados de Fase 0 y sensibilidad, mejor conjunto por horizonte y efecto
del horizonte, horizontes sin conjuntos factibles y anomalías, y una lista
de SUPUESTOS QUE EL USUARIO DEBE VALIDAR.

Uso:
    python fase5_informe.py
"""

import csv
import json
from datetime import datetime

import config


def _to_float(row: dict, key: str, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _leer_csv_sim() -> list:
    if not config.CSV_SIMULACIONES.exists():
        return []
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _cargar_json(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def seccion_configuracion() -> str:
    return f"""## Configuración usada

- Modelo PLECS: `{config.RUTA_MODELO_PLECS.name}`
- Horizontes estudiados: {config.HORIZONTES} (5 horizontes, no 10 — ver nota de
  supuestos; N>5 se consideró redundante por decisión del usuario).
- Horizonte de referencia (Fase 2, sensibilidad): N={config.HORIZONTE_REFERENCIA}
- Pesos fijos del control de corrientes: Q_Val={config.Q_VAL}, R_Val={config.R_VAL}
- Pesos base (caso base, Prueba 1 de cada bloque):
  {", ".join(f"{k}={v}" for k, v in config.PESOS_BASE.items())}
- T_SIM = {config.T_SIM} s
- Ventana de evaluación: [T_SIM − {config.T_VENTANA} s, T_SIM]
- Jerarquía de selección (sección 3): P0=validez, P1=min |media(v_cap)-150V|,
  P2=min oscilación v_cap (objetivo principal, Pareto con P1 en Optuna),
  P3=desempate por I.DC (|media| luego oscilación). i_circ es informativo.
- Tolerancias: OSC_MAX={config.OSC_MAX} V (referencia visual, ya no restricción
  dura), TOL_V_MEDIA={config.TOL_V_MEDIA} V, TOL_I_DC={config.TOL_I_DC} A
  (offset de régimen permanente medido empíricamente, no decae con más tiempo
  de simulación)
- Restricciones de igualdad: q11=q22, q44=q55 (simetría física); r11, r22
  varían independientemente. 5 variables de decisión efectivas.
- Rango de búsqueda: {config.RANGO_LOG10} décadas (log10) respecto a la base,
  límite absoluto {config.RANGO_LOG10_LIMITE}
- Presupuesto por horizonte: {config.PRUEBAS_MIN_POR_HORIZONTE}-{config.PRUEBAS_MAX_POR_HORIZONTE}
  pruebas, paciencia={config.PACIENCIA}
- Semilla: {config.SEMILLA}
- Ejecución: multi-máquina coordinada vía GitHub
  ({config.GITHUB_REPO_URL}); cada máquina mantiene su propio estudio Optuna
  (sampler no compartido), pero los resultados se comparten vía
  simulaciones.csv, evitando duplicar simulaciones exactas entre máquinas.
"""


def seccion_metricas() -> str:
    return f"""## Definiciones de las métricas y su justificación

Todas las integrales se calculan con trapecios respecto al tiempo
(`numpy.trapezoid`), no con el promedio simple de las muestras, porque PLECS
usa paso de tiempo variable y puede repetir instantes en los eventos.

- **Ventana de evaluación**: [T_SIM − 0.5 s, T_SIM]. Se usan 0.5 s porque
  contienen un número entero de periodos de 4 Hz (2 periodos) y de 50 Hz
  (25 periodos). Un solo periodo de 4 Hz (0.25 s) contiene 12.5 periodos de
  50 Hz y sesgaría el cálculo del RMS. También se guarda, solo como dato
  informativo, el RMS en el último periodo de 0.25 s (columna
  `rms_icirc_T025`).
- **RMS(x)** = sqrt(∫x² dt / T_ventana).
- **Oscilación del capacitor** = pico-pico (máx − mín) en la ventana,
  medida DESPUÉS del transitorio inicial (la ventana ya excluye el primer
  {config.T_SIM - config.T_VENTANA:.1f} s de la simulación).
- **RMSE_vcap** = máximo sobre los 6 capacitores de RMS(v_k − 150V) en la
  ventana.
- **ITAE** = máximo sobre los 6 capacitores de ∫t·|v_k − 150V| dt, sobre
  TODA la simulación (0 a T_SIM), no solo la ventana.
- **Régimen permanente**: compara la ventana final con la anterior
  [T_SIM − 1.0 s, T_SIM − 0.5 s]. Exige |Δmedia| ≤ {config.TOL_REGIMEN_MEDIA} V,
  |Δosc| ≤ {config.TOL_REGIMEN_OSC} V y |ΔRMS i_circ| ≤ {config.TOL_REGIMEN_RMS_PCT*100:.0f}%
  (i_circ se usa aquí solo como señal auxiliar de estabilidad, no como criterio
  de selección). Si no se cumple, estado = NO_ESTACIONARIO (falla P0).

Validadas con señales sintéticas (ver `metricas.py`, función
`run_self_tests()`): un seno con paso de tiempo NO uniforme da RMS = A/√2 con
error < 0.1%; un pico-pico conocido se mide correctamente; la amplitud por
Fourier de un seno de 4 Hz es correcta.
"""


def seccion_fase0() -> str:
    return """## Resultados de la Fase 0 (reconocimiento y verificación)

Verificado empíricamente contra PLECS real:
- Las constantes de horizonte y pesos (N, NrowG, NrowA en los C-Scripts
  "Mitigation/MPC Control\\nCapacitor/C-Script1" y
  "Mitigation/MPC\\nControl Corrientes/Optimization"; n en
  InitializationCommands) se leen y escriben correctamente vía XML-RPC
  (parámetro "Declarations"), sin necesidad de GUI ni recompilar
  manualmente — PLECS recompila al simular.
- Se confirmó n = N = NrowG/2 = NrowA/4 como relación fija del horizonte
  entre los dos bloques de control MPC.
- El modelo pasó por varias correcciones (ver sección de supuestos): v0
  cambiada de cuadrada a trapezoidal (definitivo, reduce picos de voltaje),
  capacitancia C cambiada a 2200e-6, pesos reajustados en consecuencia.
- Con el modelo y PESOS_BASE actuales, el caso base CONVERGE: medias de
  v_cap cercanas a 150V, oscilación bien por debajo de OSC_MAX. I.DC se
  estabiliza en un offset que no decae con más tiempo de simulación —
  confirmado idéntico en T_SIM=10s y T_SIM=20s, por eso TOL_I_DC se ajustó
  a un valor alcanzable (3A) en vez de la estimación original de 5 mA.
"""


def seccion_sensibilidad() -> str:
    conclusiones = _cargar_json(config.RESULTADOS_DIR / "fase2_conclusiones.json")
    if conclusiones is None:
        return "## Resultados de la sensibilidad (Fase 2)\n\n(fase2_sensibilidad.py no se ha corrido todavía.)\n"

    lineas = ["## Resultados de la sensibilidad (Fase 2)\n",
              f"Barrido de cada peso ×10^(−3..+3) respecto al valor base, en N={config.HORIZONTE_REFERENCIA}.\n"]
    for peso, c in conclusiones.items():
        lineas.append(f"- **{peso}**: {c.get('accion')} — {c.get('nota')}")
    return "\n".join(lineas) + "\n"


def seccion_resultados_por_horizonte() -> str:
    seleccion = _cargar_json(config.RESULTADOS_DIR / "fase4_seleccion.json")
    if seleccion is None:
        return "## Mejor conjunto por horizonte\n\n(fase4_seleccion.py no se ha corrido todavía.)\n"

    lineas = ["## Mejor conjunto por horizonte y efecto del horizonte\n"]
    lineas.append("| Horizonte | N° simulaciones | N° factibles | Mejor sim_id | "
                   "Osc v_cap P2 (V) | \\|media-150V\\| P1 (V) |")
    lineas.append("|---|---|---|---|---|---|")

    horizontes_sin_factibles = []
    for h_str, bloque in sorted(seleccion.items(), key=lambda kv: int(kv[0])):
        no_cumple = set(bloque.get("no_cumple_ids", []))
        candidatos = [p for p in bloque["pruebas_2_a_10"] if p["id"] not in no_cumple]
        if candidatos:
            mejor = candidatos[0]
            lineas.append(f"| {h_str} | {bloque['n_simulaciones']} | {bloque['n_factibles']} | "
                           f"{mejor['id']} | {mejor.get('osc_max')} | {mejor.get('desv_media_max')} |")
        else:
            lineas.append(f"| {h_str} | {bloque['n_simulaciones']} | {bloque['n_factibles']} | "
                           f"— | — | — |")
            horizontes_sin_factibles.append(h_str)

    lineas.append("")
    if horizontes_sin_factibles:
        lineas.append(f"### Horizontes SIN 9 conjuntos diversos: {', '.join(horizontes_sin_factibles)}\n")
        lineas.append("Esos bloques se completaron con los mejores candidatos factibles restantes "
                       "(aunque no diversos entre sí), marcados NO DIVERSO en el Excel. La validez "
                       "P0 nunca se relajó; solo se relajó la exigencia de diversidad.\n")
    else:
        lineas.append("Todos los horizontes tuvieron al menos un conjunto factible.\n")

    return "\n".join(lineas)


def seccion_supuestos() -> str:
    return """## SUPUESTOS QUE EL USUARIO DEBE VALIDAR

1. **v0 trapezoidal (cambio definitivo, 2026-10-19)**: la especificación
   original (sección 1) pedía v0 cuadrada; el usuario volvió a trapezoidal
   de forma intencional y definitiva ("cambios abruptos en v0 generaban
   picos en el voltaje, el cambio de signo más suave es menos demandante al
   sistema"). VALIDAR que esta decisión sigue siendo la deseada a largo
   plazo del estudio.
2. **Jerarquía de selección reemplazada (2026-10-19)**: el objetivo
   principal pasó de minimizar RMS de corriente circulante a minimizar la
   oscilación de v_cap (P2), con P1=desviación de la media y P3=desempate
   por I.DC. i_circ pasó a ser solo informativo. VALIDAR que esta jerarquía
   captura correctamente la intención real del estudio (el nombre del
   archivo del modelo, "Osc. Cap casi en 10V", sugiere que la oscilación es
   efectivamente la preocupación principal).
3. **TOL_I_DC relajado a 3A**: medido empíricamente que I.DC se estabiliza
   en un offset de ~2.37A con el caso base que NO decae con más tiempo de
   simulación (idéntico en T_SIM=10s y 20s) — no es un transitorio lento,
   es el régimen permanente real. VALIDAR si este offset es aceptable desde
   el punto de vista de ingeniería, o si indica un ajuste pendiente en el
   modelo/control que debería investigarse en vez de simplemente relajar la
   tolerancia.
4. **C=2200e-6 y pesos reajustados**: la capacitancia física de los
   submódulos se cambió de un valor normalizado (C=1) a 2200e-6 F, con los
   pesos del MPC reajustados en consecuencia (q11=q22=150, q33=300,
   r11=r22=3, comentado en el propio código como "×100 por C 10 veces
   menor"). VALIDAR que 2200e-6 F es el valor físico correcto deseado.
5. **5 horizontes, no 10**: las instrucciones originales y la plantilla
   Excel mencionan 10 horizontes; el usuario confirmó (2026-09-30) que el
   estudio real cubre solo N=1..5 (N>5 es redundante). VALIDAR que esto
   sigue siendo correcto.
6. **Restricciones de igualdad q11=q22, q44=q55**: confirmado con el
   usuario (2026-10-10) como simetría física del sistema. r11 y r22 varían
   independientemente. VALIDAR que esto sigue siendo correcto con el modelo
   actual.
7. **Osc. Cap como fuente de v_cap**: el scope "Osc. Cap" reemplazó a
   "Voltaje Capacitores/Scope1" como fuente de v_cap (confirmado por el
   usuario que ambos muestran la misma señal — verificado exportando
   ambos: mismo formato, mismo valor inicial 148V). VALIDAR que esto sigue
   siendo así en futuras versiones del modelo.
8. **Caso Bryson no incluido**: la sección 7 Fase 1 menciona opcionalmente
   calcular un punto inicial con la regla de Bryson
   (q_ii=1/x_i,max², r_jj=1/u_j,max²). El usuario confirmó que no tiene los
   valores máximos físicos definidos; este punto se dejó fuera del estudio.
9. **Estado de Optuna no compartido entre máquinas**: cada máquina mantiene
   su propio sampler bayesiano por horizonte (sin ver los puntos que otra
   máquina ya probó al elegir el siguiente). Los RESULTADOS sí se comparten
   vía simulaciones.csv (evitando duplicar simulaciones exactas), pero la
   eficiencia de la búsqueda bayesiana es menor que con un sampler
   compartido. Confirmado como aceptable por el usuario (2026-10-04).
"""


def main():
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    partes = [
        f"# Informe: ajuste de pesos del MPC de capacitores\n\n"
        f"Generado: {datetime.now().isoformat(timespec='seconds')}\n",
        seccion_configuracion(),
        seccion_metricas(),
        seccion_fase0(),
        seccion_sensibilidad(),
        seccion_resultados_por_horizonte(),
        seccion_supuestos(),
    ]

    texto = "\n".join(partes)
    with open(config.INFORME_MD, "w", encoding="utf-8") as f:
        f.write(texto)

    print(f"Informe guardado en {config.INFORME_MD}")


if __name__ == "__main__":
    main()
