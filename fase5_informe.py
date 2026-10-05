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
- Tolerancias: OSC_MAX={config.OSC_MAX} V, TOL_V_MEDIA={config.TOL_V_MEDIA} V,
  TOL_I_DC={config.TOL_I_DC} A (ver nota de supuestos sobre el reemplazo del
  criterio original de i_ac)
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
  |Δosc| ≤ {config.TOL_REGIMEN_OSC} V y |ΔRMS i_circ| ≤ {config.TOL_REGIMEN_RMS_PCT*100:.0f}%.
  Si no se cumple, estado = NO_ESTACIONARIO (falla P0).

Validadas con señales sintéticas (ver `metricas.py`, función
`run_self_tests()`): un seno con paso de tiempo NO uniforme da RMS = A/√2 con
error < 0.1%; un pico-pico conocido se mide correctamente; la amplitud por
Fourier de un seno de 4 Hz es correcta.
"""


def seccion_fase0() -> str:
    return """## Resultados de la Fase 0 (reconocimiento y verificación)

Verificado empíricamente contra PLECS real:
- Las constantes de horizonte y pesos (N, NrowG, NrowA en los C-Scripts
  "Mitigation/C-Script" y "Mitigation/MPC\\nControl Corrientes/Optimization";
  n en InitializationCommands) se leen y escriben correctamente vía XML-RPC
  (parámetro "Declarations"), sin necesidad de GUI ni recompilar
  manualmente — PLECS recompila al simular.
- Se confirmó n = N = NrowG/2 = NrowA/4 como relación fija del horizonte
  entre los dos bloques de control MPC.
- Las matrices de predicción (H, F, B, Dk, Uk) están correctamente
  parametrizadas por N vía arrays dimensionados y bucles — no hardcodeadas.
- **El caso base actual (PESOS_BASE de config.py) DIVERGE**: no alcanza
  régimen permanente. Se observó numéricamente la divergencia: el voltaje de
  capacitor y la corriente I.DC alcanzan valores de cientos/miles en menos
  de 1 ms de tiempo simulado. Esto bloquea el punto de control formal de la
  Fase 0 — ver sección de supuestos pendientes de validar.
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
    lineas.append("| Horizonte | N° simulaciones | N° factibles | Mejor sim_id | RMS i_circ (A) | Osc (V) |")
    lineas.append("|---|---|---|---|---|---|")

    horizontes_sin_factibles = []
    for h_str, bloque in sorted(seleccion.items(), key=lambda kv: int(kv[0])):
        no_cumple = set(bloque.get("no_cumple_ids", []))
        candidatos = [p for p in bloque["pruebas_2_a_10"] if p["id"] not in no_cumple]
        if candidatos:
            mejor = candidatos[0]
            lineas.append(f"| {h_str} | {bloque['n_simulaciones']} | {bloque['n_factibles']} | "
                           f"{mejor['id']} | {mejor.get('rms_icirc_peor')} | {mejor.get('osc_max')} |")
        else:
            lineas.append(f"| {h_str} | {bloque['n_simulaciones']} | {bloque['n_factibles']} | "
                           f"— | — | — |")
            horizontes_sin_factibles.append(h_str)

    lineas.append("")
    if horizontes_sin_factibles:
        lineas.append(f"### Horizontes SIN conjuntos factibles: {', '.join(horizontes_sin_factibles)}\n")
        lineas.append("Esos bloques se completaron (si fue posible) con los conjuntos más cercanos "
                       "a la restricción de 10V, marcados NO CUMPLE en el Excel. La restricción de "
                       "oscilación NUNCA se relajó.\n")
    else:
        lineas.append("Todos los horizontes tuvieron al menos un conjunto factible.\n")

    return "\n".join(lineas)


def seccion_supuestos() -> str:
    return """## SUPUESTOS QUE EL USUARIO DEBE VALIDAR

1. **Caso base divergente**: con los pesos actuales de `config.PESOS_BASE`
   (q11=1.0, q22=1.0, q33=10000.0, q44=10.0, q55=10.0, r11=1e-2, r22=1e-2),
   el sistema diverge (no alcanza régimen permanente). El usuario indicó que
   esto es "un problema de pesos" y no del código de control, y pidió seguir
   construyendo el pipeline confiando en que Optuna (Fase 3) encuentre
   puntos factibles. VALIDAR si efectivamente existen pesos que estabilicen
   el sistema dentro del rango de búsqueda configurado (RANGO_LOG10), antes
   de confiar en los resultados de este informe.
2. **5 horizontes, no 10**: las instrucciones originales y la plantilla
   Excel mencionan 10 horizontes; el usuario confirmó (2026-09-30) que el
   estudio real cubre solo N=1..5 (N>5 es redundante). VALIDAR que esto
   sigue siendo correcto.
3. **Criterio P0(c) reemplazado**: el criterio original de validez
   (amplitud de i_ac dentro de ±10% de I_AC_REF≈16A) se reemplazó por
   |I.DC| < 5 mA en la ventana de evaluación, porque no se encontró un
   scope exportable para i_ac/Is (el punto "Iout" del nivel superior no es
   una ventana de scope real). VALIDAR que esta sustitución captura
   correctamente la intención original (evitar que el control "reduzca" la
   corriente circulante dejando de entregar potencia al puerto AC).
4. **Mapeo de señales v_cap**: se asume que las 6 señales de voltaje de
   capacitor (Plot1=ap,bp,cp / Plot2=an,bn,cn del scope "Voltaje
   Capacitores/Scope") corresponden en ese orden a los 6 clusters del
   esquema de nivel superior. El usuario confirmó este mapeo pero señaló
   que debían revisarse las 6 señales y no asumir ciegamente la simetría
   ap≈an, bp≈bn, cp≈cn. VALIDAR en los resultados reales si esa simetría se
   cumple o no.
5. **Caso Bryson no incluido**: la sección 7 Fase 1 menciona opcionalmente
   calcular un punto inicial con la regla de Bryson
   (q_ii=1/x_i,max², r_jj=1/u_j,max²). El usuario confirmó que no tiene los
   valores máximos físicos definidos; este punto se dejó fuera del estudio.
6. **Estado de Optuna no compartido entre máquinas**: cada máquina mantiene
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
