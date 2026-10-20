"""
config.py — Configuración central del estudio de pesos MPC (control de capacitores).

Todo el código del estudio debe leer sus parámetros de acá. No hardcodear valores
en otros scripts.

Campos pendientes de Fase 0 (ver INSTRUCCIONES.md sección 7, Fase 0):
- T_SIM: se fija tras simular el caso base y verificar asentamiento + régimen permanente.
Debe confirmarse en el punto de control de Fase 0 antes de avanzar a la Fase 1.

MODELO ACTUALIZADO (2026-10-10): el usuario reemplazó el modelo PLECS por una
versión corregida ("trapezoide y con 2V0") que soluciona varios errores,
incluyendo que la señal v0 se enviaba trapezoidal en vez de cuadrada (sección
1 original: "v0: señal signo (cuadrada) de 50 Hz"). Esto invalida TODOS los
resultados de divergencia obtenidos con el modelo anterior durante la
búsqueda manual de pesos estables — no eran representativos del sistema
real. Además, durante esa búsqueda se encontraron dos bugs adicionales en el
pipeline (no en el modelo): (1) el modelo tenía TimeSpan=4s configurado
manualmente (el usuario lo había bajado porque el sistema solía divergir
cerca de t=5s), desincronizado de config.T_SIM, por lo que toda simulación
se cortaba a los 4s sin que el solver llegara a mostrar si era realmente
estable más allá — ahora aplicar_punto() sincroniza TimeSpan con T_SIM en
cada llamada; (2) el scope de v_cap apuntaba a "Scope" en vez de "Scope1"
(el de voltajes sin transformar), lo que daba lecturas incorrectas.

MODELO ACTUALIZADO DE NUEVO (2026-10-19): el usuario volvió a cambiar v0 de
cuadrada a TRAPEZOIDAL, esta vez de forma DEFINITIVA e intencional —
confirmado explícitamente: "cambios abruptos en v0 generaban picos en el
voltaje, el cambio de signo más suave es menos demandante al sistema". Esto
reemplaza la especificación de la sección 1 original de INSTRUCCIONES.md
("v0: señal signo (cuadrada) de 50 Hz" → ahora trapezoidal). También cambió
el valor de capacitancia C a 2200e-6 (antes C=1, un valor por unidad/
normalizado) de forma intencional. Nuevo modelo: "v0Trapezoidal - C en
2200e-6 - Osc. Cap casi en 10V.plecs". Mismo bloque activo C-Script1 que el
modelo anterior, pero con pesos reajustados por el cambio de C (ver
comentarios en el propio C-Script1: "r11 ×100 por C 10 veces menor").
"""

from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────────
RUTA_ESTUDIO = Path(__file__).parent
RUTA_MODELO_PLECS = Path(
    r"C:\Users\danie\Downloads\v0Trapezoidal - C en 2200e-6 - Osc. Cap casi en 10V.plecs"
)
SCRIPT_EXISTENTE = RUTA_ESTUDIO / "plecs_runner.py"  # wrapper reutilizado/extendido del script original
PLANTILLA_EXCEL = "Pruebas_por_peso_MPC._Modelo_promedio.xlsx"
EXCEL_RESULTADOS = RUTA_ESTUDIO / "resultados" / "Pruebas_por_peso_MPC_resultados.xlsx"

# ── Modelo PLECS ─────────────────────────────────────────────────────────────
MODEL_NAME = "v0Trapezoidal - C en 2200e-6 - Osc. Cap casi en 10V"
PLECS_URL = "http://localhost:1080/RPC2"

# Bloque C-Script del MPC de capacitores: contiene N (horizonte) y los 7 pesos
# (q11, q22, q33, q44, q55, r11, r22) como #define. CONFIRMADO con el usuario:
# el bloque activo/conectado es "C-Script1" (hay otros C-Script/C-Script2 en
# el modelo que son copias de prueba, no tocar). El subsistema contenedor
# tiene salto de línea literal en su nombre real ("MPC Control\nCapacitor").
BLOQUE_CAPACITORES = f"{MODEL_NAME}/Mitigation/MPC Control\nCapacitor/C-Script1"

# Bloque C-Script del MPC de corrientes circulantes: contiene NrowG (= 2*N) y
# NrowA (= 2*NrowG = 4*N), y los pesos fijos Q_VAL=1, R_VAL=1e-3 (NO modificar
# estos dos, solo NrowG y NrowA). OJO: el nombre real del subsistema en PLECS
# contiene un salto de línea literal ("MPC\nControl Corrientes") — confirmado
# vía plecs.getModelTree; replicar tal cual al construir la ruta. El bloque
# activo sigue siendo "Optimization" sin sufijo (Optimization1 vacío/sin usar).
BLOQUE_CORRIENTES = f"{MODEL_NAME}/Mitigation/MPC\nControl Corrientes/Optimization"

# Bloques que NO dependen del horizonte (muxes/sin usar): Mitigation/MPC\n
# Control Corrientes/Optimization1, Predictions. No tocar sus #define.

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
# CAMBIO DE ALCANCE (2026-10-19, confirmado con el usuario): el estudio ahora
# es SOLO para horizonte N=1 — ya no 5 horizontes (1-5) ni 10. PESOS_BASE
# (abajo) son específicos de N=1. El Excel tendrá un solo bloque en vez de 5.
HORIZONTES = [1]
HORIZONTE_REFERENCIA = 1  # único horizonte del estudio

# ── Pesos del control de capacitores ────────────────────────────────────────
# Nombres de las variables (#define) en BLOQUE_CAPACITORES.
NOMBRES_PESOS = ["q11", "q22", "q33", "q44", "q55", "r11", "r22"]

# RESTRICCIONES DE IGUALDAD confirmadas con el usuario (2026-10-10): q11 debe
# ser siempre igual a q22, y q44 siempre igual a q55 (simetría física del
# sistema). r11 y r22 SÍ pueden variar independientemente entre sí. Esto
# reduce las variables de decisión efectivas de 7 a 5: q11(=q22), q33,
# q44(=q55), r11, r22. Los scripts de Fase 2/3 deben respetar esto: al variar
# q11 también hay que variar q22 en conjunto (y lo mismo para q44/q55), no
# tratarlos como ejes independientes del espacio de búsqueda.
PESOS_IGUALES = [("q11", "q22"), ("q44", "q55")]

# CONFIRMADO con el usuario (2026-10-19): valores actuales del modelo
# "v0Trapezoidal - C en 2200e-6 - Osc. Cap casi en 10V" — caso base. Pesos
# reajustados respecto a la versión anterior por el cambio de capacitancia
# (comentario en el propio C-Script1: "r11 ×100 por C 10 veces menor";
# "q33 antes 1.0: ahora Δ0 se controla activamente").
PESOS_BASE = {
    "q11": 150.0,
    "q22": 150.0,
    "q33": 300.0,
    "q44": 1.0,
    "q55": 1.0,
    "r11": 3.0,
    "r22": 3.0,
}

# Valor de capacitancia de los submódulos (parámetro físico, #define C en
# BLOQUE_CAPACITORES). Cambiado intencionalmente por el usuario (2026-10-19)
# de C=1 (normalizado) a C=2200e-6 (valor real en Faradios). NO es un peso
# de decisión del MPC — es un parámetro físico fijo del modelo, documentado
# acá solo como referencia.
C_SUBMODULO = 2200e-6

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
# CORRECCIÓN (2026-10-04): el scope de voltajes de capacitor SIN TRANSFORMAR
# es "Voltaje Capacitores/Scope1" (confirmado con el usuario), no "Scope" (que
# usamos por error toda la sesión anterior — probablemente muestra otra
# señal, posiblemente transformada/derivada, lo que explicaba valores
# irreales como -266V o 439V en pruebas de "divergencia" que en realidad
# estaban leyendo el scope equivocado). NOTA: a diferencia de "MPC\nControl
# Corrientes" (que sí tiene salto de línea en el título real de ventana),
# "Voltaje Capacitores" usa un ESPACIO normal en el título de ventana —
# confirmado enumerando las ventanas abiertas directamente (el \n que muestra
# plecs.getModelTree para el subsistema interno no siempre coincide con el
# título real de la ventana del scope).
# CAMBIO (2026-10-19): el usuario confirmó que "Osc. Cap" muestra exactamente
# lo mismo que "Voltaje Capacitores/Scope1" (voltajes de capacitor sin
# transformar, 6 trazas) — verificado exportando ambos: mismo formato (7
# columnas, tiempo + 6 trazas "Vm:Measured voltage"), mismo valor inicial
# 148V. Se usa "Osc. Cap" como fuente ÚNICA de v_cap de ahora en más (un
# scope menos que mantener abierto); ya no hace falta abrir
# "Voltaje Capacitores/Scope1" por separado.
SCOPES = {
    "v_cap": f"{MODEL_NAME}/Osc. Cap",
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
# CONFIRMADO (2026-10-10) con el modelo corregido ("trapezoide y con 2V0"):
# el caso base converge correctamente con T_SIM=10s — medias v_cap≈150V,
# oscilación=0.08V pico-pico, idénticos a los obtenidos con T_SIM=20s (misma
# prueba repetida con el doble de tiempo dio exactamente los mismos valores),
# confirmando régimen permanente alcanzado bien antes de los 10s.
T_SIM = 10.0

# ── Tolerancias y criterios (sección 2 y 4) ─────────────────────────────────
OSC_MAX = 10.0  # V
# CONFIRMADO con el usuario (2026-09-30): pico-pico (máx - mín), medido en la
# ventana de evaluación [T_SIM-0.5s, T_SIM] (ya excluye el transitorio inicial).
DEF_OSCILACION = "pico-pico"
# CAMBIO DE CRITERIO P0(c), confirmado con el usuario (2026-09-30): ya no se usa
# i_ac (no hay scope exportable para esa señal). Se reemplaza por la condición
# |I.DC| < TOL_I_DC en la ventana de evaluación (post-estabilización).
# AJUSTE (2026-10-10): con el modelo corregido, el caso base converge muy bien
# en v_cap (medias ≈150V, oscilación 0.08V) pero I.DC se estabiliza en un
# offset de ~2.37A que NO decae con más tiempo de simulación (idéntico en
# t=10s y t=20s — confirmado empíricamente, no es un transitorio lento). Los
# 5 mA originales eran una estimación de referencia, no una medición real del
# sistema. Confirmado con el usuario: relajar a una tolerancia alcanzable.
TOL_I_DC = 3.0        # A, |I.DC| en la ventana de evaluación
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

TOL_EMPATE = 0.02       # 2% (confirmado 2026-10-19: tolerancia de empate en P1 y P2)
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
