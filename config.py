"""
config.py — Configuración central del estudio de pesos MPC (control de capacitores).

Todo el código del estudio debe leer sus parámetros de acá. No hardcodear valores
en otros scripts.

Campos pendientes de Fase 0 (ver INSTRUCCIONES.md sección 7, Fase 0):
- T_SIM: se fija tras simular el caso base y verificar asentamiento + régimen permanente.
  Actualmente en placeholder provisional (10s) para desarrollo del pipeline — el
  caso base con PESOS_BASE actuales diverge (no cumple P0), pendiente de que el
  usuario encuentre/confirme pesos base que sí estabilicen.
Debe confirmarse en el punto de control de Fase 0 antes de avanzar a la Fase 1.
"""

from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────────
RUTA_ESTUDIO = Path(__file__).parent
RUTA_MODELO_PLECS = Path(
    r"C:\Users\danie\Downloads\mpc_pruebas\MMC_sinmodulacion - Con MPC - Corrección Predicciones.plecs"
)
SCRIPT_EXISTENTE = RUTA_ESTUDIO / "plecs_runner.py"  # wrapper reutilizado/extendido del script original
PLANTILLA_EXCEL = "Pruebas_por_peso_MPC._Modelo_promedio.xlsx"
EXCEL_RESULTADOS = RUTA_ESTUDIO / "resultados" / "Pruebas_por_peso_MPC_resultados.xlsx"

# ── Modelo PLECS ─────────────────────────────────────────────────────────────
MODEL_NAME = "MMC_sinmodulacion - Con MPC - Corrección Predicciones"
PLECS_URL = "http://localhost:1080/RPC2"

# Bloque C-Script del MPC de capacitores: contiene N (horizonte) y los 7 pesos
# (q11, q22, q33, q44, q55, r11, r22) como #define.
BLOQUE_CAPACITORES = f"{MODEL_NAME}/Mitigation/C-Script"

# Bloque C-Script del MPC de corrientes circulantes: contiene NrowG (= 2*N) y
# NrowA (= 2*NrowG = 4*N), y los pesos fijos Q_VAL=1, R_VAL=1e-3 (NO modificar
# estos dos, solo NrowG y NrowA). OJO: el nombre real del subsistema en PLECS
# contiene un salto de línea literal ("MPC\nControl Corrientes") — confirmado
# vía plecs.getModelTree; replicar tal cual al construir la ruta.
BLOQUE_CORRIENTES = f"{MODEL_NAME}/Mitigation/MPC\nControl Corrientes/Optimization"

# Bloques que NO dependen del horizonte (muxes, confirmado con el usuario
# 2026-09-30): Mitigation/MPC\nControl Corrientes/Optimization1,
# Mitigation/Optimization1, Predictions. No tocar sus #define.

# La variable de horizonte "n" (además de N, NrowG, NrowA) vive en
# InitializationCommands (Simulation Parameters > Initialization), no en un C-Script.
VARIABLE_HORIZONTE_INIT = "n"  # vía InitializationCommands (set_params existente)
VARIABLE_HORIZONTE_CAP = "N"  # #define en BLOQUE_CAPACITORES
VARIABLE_HORIZONTE_CORR = "NrowG"  # #define en BLOQUE_CORRIENTES, DEBE valer 2*N
VARIABLE_HORIZONTE_CORR_A = "NrowA"  # #define en BLOQUE_CORRIENTES, DEBE valer 4*N (= 2*NrowG)

def nrow_g(n_horizonte: int) -> int:
    return 2 * n_horizonte

def nrow_a(n_horizonte: int) -> int:
    return 4 * n_horizonte

# ── Horizontes a estudiar ────────────────────────────────────────────────────
# CONFIRMADO con el usuario (2026-09-30): solo 5 horizontes, no 10 — más allá de
# N=5 el estudio es redundante. HORIZONTE_REFERENCIA = mediana por defecto.
HORIZONTES = [1, 2, 3, 4, 5]
HORIZONTE_REFERENCIA = 3  # mediana de HORIZONTES

# ── Pesos del control de capacitores ────────────────────────────────────────
# Nombres de las variables (#define) en BLOQUE_CAPACITORES.
NOMBRES_PESOS = ["q11", "q22", "q33", "q44", "q55", "r11", "r22"]

# CONFIRMADO con el usuario (2026-09-30): valores actuales del modelo (caso base).
PESOS_BASE = {
    "q11": 1.0,
    "q22": 1.0,
    "q33": 10000.0,
    "q44": 10.0,
    "q55": 10.0,
    "r11": 1.0e-2,
    "r22": 1.0e-2,
}

# Pesos FIJOS del control de corrientes circulantes (NO modificar, sección 1).
Q_VAL = 1.0
R_VAL = 1.0e-3

# ── Señales / scopes (confirmados con el usuario, 2026-09-30) ──────────────
# v_cap: 6 señales (una por cluster: ap, bp, cp, an, bn, cn). Se esperan ap≈an,
# bp≈bn, cp≈cn por simetría, pero se miden y registran las 6 (sección 4: "si hay
# más, inclúyelas todas").
#
# CAMBIO DE CRITERIO confirmado con el usuario (2026-09-30): el scope "Iout"
# (señal "Is") NO es una ventana de scope real — pywinauto no pudo exportarlo
# (falla al conectar la ventana). Se reemplaza el criterio P0(c) de amplitud de
# i_ac por la señal del scope "I. DC" del nivel superior, que debe estabilizarse
# cerca de 0 A. Ver TOL_I_DC más abajo.
SCOPES = {
    "v_cap": f"{MODEL_NAME}/Voltaje Capacitores/Scope",
    "i_circ": f"{MODEL_NAME}/C. Circul",
    "i_dc": f"{MODEL_NAME}/I. DC",
}

# Orden confirmado de las trazas en cada scope exportado:
SENALES = {
    "v_cap": ["Vcap_ap", "Vcap_bp", "Vcap_cp", "Vcap_an", "Vcap_bn", "Vcap_cn"],
    "i_circ": ["i_circ_alpha", "i_circ_beta"],
    "i_dc": ["Idc"],
}

# ── Parámetros físicos fijos (sección 1, NO modificar) ──────────────────────
F_AC = 4.0       # Hz
F_V0 = 50.0      # Hz
V_REF = 150.0    # V

# ── Ventana y tiempo de simulación ──────────────────────────────────────────
T_VENTANA = 0.5  # s (mcm de 0.25 s y 0.02 s)
# [PROVISIONAL] T_SIM=10s solo para desarrollar y probar el pipeline (metricas.py,
# exportación, Excel). Confirmado con el usuario (2026-09-30): el caso base actual
# DIVERGE (I.DC no converge a ~0, las medias de v_cap se alejan de 150V — "el
# capacitor explota"), por lo que NO cumple P0. El usuario va a revisar/corregir
# el control del MPC de capacitores antes de que las Fases 0-6 con resultados
# reales puedan ejecutarse. Este valor DEBE recalcularse en la Fase 0 real,
# una vez que el caso base converja, siguiendo el procedimiento de la sección 7.
T_SIM = 10.0

# ── Tolerancias y criterios (sección 2 y 4) ─────────────────────────────────
OSC_MAX = 10.0  # V
# CONFIRMADO con el usuario (2026-09-30): pico-pico (máx - mín), medido en la
# ventana de evaluación [T_SIM-0.5s, T_SIM] (ya excluye el transitorio inicial).
DEF_OSCILACION = "pico-pico"
# CAMBIO DE CRITERIO P0(c), confirmado con el usuario (2026-09-30): ya no se usa
# i_ac (no hay scope exportable para esa señal). Se reemplaza por la condición
# |I.DC| < TOL_I_DC en la ventana de evaluación (post-estabilización).
TOL_I_DC = 0.005      # A (5 mA), |I.DC| en la ventana de evaluación
TOL_V_MEDIA = 2.0     # V, diferencia permitida entre media de cada capacitor y V_REF

# Régimen permanente (ventana final vs anterior, sección 4)
TOL_REGIMEN_MEDIA = 0.2   # V
TOL_REGIMEN_OSC = 0.2     # V
TOL_REGIMEN_RMS_PCT = 0.02  # 2%

# ── Rango y presupuesto de búsqueda (Fase 2 y 3) ────────────────────────────
RANGO_LOG10 = (-3, 3)  # décadas alrededor de PESOS_BASE
RANGO_LOG10_LIMITE = (-6, 6)  # límite absoluto (sección 7, Fase 3)

PRUEBAS_MIN_POR_HORIZONTE = 40
PRUEBAS_MAX_POR_HORIZONTE = 80
PACIENCIA = 20
PRUEBAS_EXTRA_EXPLORATORIAS = 20  # si quedan <9 candidatos factibles diversos al llegar al máximo

TOL_EMPATE = 0.01       # 1% (criterio P3)
DIST_MIN_LOG10 = 0.301  # equivale a factor 2 (criterio Fase 4)

# ── Reproducibilidad y límites de ejecución ─────────────────────────────────
SEMILLA = 42
TIMEOUT_SIM = 120.0  # s
INCLUIR_CASO_BASE_COMO_PRUEBA_1 = True

# [PROVISIONAL] Tolerancia de repetibilidad para la Fase 6 (verificación
# final). La sección 7 pide usar "la tolerancia de repetibilidad medida en la
# Fase 0", pero esa medición real depende de que el caso base converja
# (pendiente, ver nota en T_SIM más abajo). Confirmado con el usuario
# (2026-10-04): usar 1% como placeholder laxo mientras tanto, más conservador
# que el 1e-6 relativo de la sección 6 (ese umbral es para detectar
# "resultados distintos" en repeticiones exactas del caso base, un chequeo
# más estricto que no aplica aún sin Fase 0 real). DEBE reemplazarse por la
# medición empírica real antes de confiar en los resultados de Fase 6.
TOL_REPETIBILIDAD = 0.01

# ── Ejecución multi-máquina (coordinación vía GitHub) ───────────────────────
import socket
MAQUINA_ID = socket.gethostname()
GITHUB_REPO_URL = "https://github.com/tr1pl3z3r0/mpc-capacitor-weights-study.git"
# Tiempo máximo que puede quedar una fila en estado CORRIENDO antes de
# considerarse abandonada (máquina caída/desconectada) y poder reclamarse de
# nuevo por otra máquina.
TIMEOUT_CLAIM_S = 600  # 10 min (generoso: TIMEOUT_SIM=120s + exportación + red)

LIMITE_TOTAL_SIMULACIONES = 1200  # sección 6: detenerse y preguntar si se va a superar

# ── Archivos de salida ───────────────────────────────────────────────────────
RESULTADOS_DIR = RUTA_ESTUDIO / "resultados"
CSV_SIMULACIONES = RESULTADOS_DIR / "simulaciones.csv"
OPTUNA_DB = RESULTADOS_DIR / "optuna.db"
FORMAS_ONDA_DIR = RESULTADOS_DIR / "formas_onda"
FIGURAS_DIR = RESULTADOS_DIR / "figuras"
INFORME_MD = RESULTADOS_DIR / "informe.md"
PROGRESO_LOG = RESULTADOS_DIR / "progreso.log"
