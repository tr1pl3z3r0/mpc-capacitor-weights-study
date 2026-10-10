"""
plecs_runner.py — Interfaz genérica con PLECS via XML-RPC + GUI.

Configurá MODEL_NAME, PLECS_URL y SCOPES antes de usar.
"""

import re
import time
import xmlrpc.client
from pathlib import Path

import numpy as np
import pandas as pd
import pyautogui
import win32api
import win32con
import win32gui
import win32process
from pywinauto import Desktop, Application

# ── Configuración ─────────────────────────────────────────────────────────────
MODEL_NAME = "MMC_sinmodulacion - Con MPC - trapezoide y con 2V0"          # nombre exacto del modelo en PLECS
PLECS_URL  = "http://localhost:1080/RPC2"

# Scopes a exportar: {clave: título_exacto_del_scope_en_PLECS}
SCOPES = {
    "scope1": f"{MODEL_NAME}/Subsistema/NombreScope1",
    "scope2": f"{MODEL_NAME}/Subsistema/NombreScope2",
}

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.1


# ── XML-RPC ───────────────────────────────────────────────────────────────────

def _server():
    return xmlrpc.client.Server(PLECS_URL)


def set_params(params: dict):
    """Escribe variables en InitializationCommands via XML-RPC.
    params = {"nombre_var": valor, ...}
    """
    _stop_simulation()
    srv = _server()
    try:
        cmd = srv.plecs.get(MODEL_NAME, "InitializationCommands")
        for name, value in params.items():
            pattern = rf"(?<![A-Za-z0-9_])({re.escape(name)})(\s*=\s*)[^\n;]+"
            cmd, n = re.subn(pattern, rf"\g<1>\g<2>{float(value)}", cmd)
            if n == 0:
                cmd = cmd.rstrip() + f"\n{name} = {float(value)}"
        srv.plecs.set(MODEL_NAME, "InitializationCommands", cmd)
    except ConnectionRefusedError:
        raise RuntimeError("No se puede conectar a PLECS en " + PLECS_URL)


def get_params(names: list) -> dict:
    """Lee variables actuales de InitializationCommands."""
    srv = _server()
    cmd = srv.plecs.get(MODEL_NAME, "InitializationCommands")
    result = {}
    for name in names:
        m = re.search(rf"{re.escape(name)}\s*=\s*([0-9eE+\-\.]+)", cmd)
        result[name] = float(m.group(1)) if m else None
    return result


# ── Edición de #define en C-Scripts (pesos MPC y horizonte) ────────────────
# Verificado empíricamente (Fase 0): el código de un bloque C-Script se lee y
# escribe con plecs.get/plecs.set usando el parámetro "Declarations". No hace
# falta GUI ni recompilar manualmente — PLECS recompila solo al simular.

def get_define(block_path: str, name: str) -> str:
    """Lee el valor actual de un #define NAME VALUE en un bloque C-Script."""
    srv = _server()
    code = srv.plecs.get(block_path, "Declarations")
    m = re.search(rf"(?<![A-Za-z0-9_])#define\s+{re.escape(name)}\s+([^\s/]+)", code)
    if not m:
        raise RuntimeError(f"No se encontró #define {name} en {block_path!r}.")
    return m.group(1)


def set_define(block_path: str, name: str, value):
    """Escribe un #define NAME VALUE existente en un bloque C-Script (no crea nuevos)."""
    srv = _server()
    code = srv.plecs.get(block_path, "Declarations")
    pattern = rf"(?<![A-Za-z0-9_])(#define\s+{re.escape(name)}\s+)[^\s/]+"
    new_code, n = re.subn(pattern, rf"\g<1>{value}", code)
    if n != 1:
        raise RuntimeError(
            f"Esperaba exactamente 1 ocurrencia de '#define {name}' en {block_path!r}, hubo {n}."
        )
    srv.plecs.set(block_path, "Declarations", new_code)


def set_defines(block_path: str, valores: dict):
    """Escribe varios #define en un mismo bloque en una sola lectura/escritura."""
    srv = _server()
    code = srv.plecs.get(block_path, "Declarations")
    for name, value in valores.items():
        pattern = rf"(?<![A-Za-z0-9_])(#define\s+{re.escape(name)}\s+)[^\s/]+"
        code, n = re.subn(pattern, rf"\g<1>{value}", code)
        if n != 1:
            raise RuntimeError(
                f"Esperaba exactamente 1 ocurrencia de '#define {name}' en {block_path!r}, hubo {n}."
            )
    srv.plecs.set(block_path, "Declarations", code)


def aplicar_punto(horizonte: int, pesos: dict, config):
    """Aplica un punto de diseño completo: horizonte (n, N, NrowG, NrowA) y los
    7 pesos del MPC de capacitores. config es el módulo config.py (para evitar
    import circular, se pasa explícitamente).

    Reglas aplicadas (ver INSTRUCCIONES.md secciones 2 y 7):
    - n = N = NrowG/2 = NrowA/4 (sincronía de horizonte entre los 2 bloques MPC).
    - Los pesos se redondean a 3 cifras significativas ANTES de escribirlos
      (regla inquebrantable 5.7: "el valor escrito en la tabla es exactamente
      el que se simuló").
    - TimeSpan del modelo (parámetro de PLECS, Simulation Parameters > Solver)
      se sincroniza con config.T_SIM. Encontrado en producción (2026-10-04):
      el modelo tenía TimeSpan=4s fijado manualmente (el usuario lo bajó de
      su valor original porque el sistema solía divergir cerca de t=5s), y
      quedó desincronizado de config.T_SIM=10, haciendo que CUALQUIER
      simulación se cortara a los 4s y se malinterpretara como "divergencia"
      cuando en realidad el solver nunca llegó a mostrar si era estable o no
      más allá de ese punto.
    """
    _stop_simulation()

    pesos_redondeados = {k: _redondear_3_cifras(v) for k, v in pesos.items()}

    srv = _server()
    srv.plecs.set(MODEL_NAME, "TimeSpan", str(config.T_SIM))

    set_params({config.VARIABLE_HORIZONTE_INIT: horizonte})

    set_defines(config.BLOQUE_CAPACITORES, {
        config.VARIABLE_HORIZONTE_CAP: horizonte,
        **pesos_redondeados,
    })

    set_defines(config.BLOQUE_CORRIENTES, {
        config.VARIABLE_HORIZONTE_CORR: 2 * horizonte,
        config.VARIABLE_HORIZONTE_CORR_A: 4 * horizonte,
    })

    return pesos_redondeados


def _redondear_3_cifras(x: float) -> float:
    """Redondea a 3 cifras significativas (regla inquebrantable 5.7)."""
    if x == 0:
        return 0.0
    from math import floor, log10
    d = 2 - int(floor(log10(abs(x))))
    return round(x, d)


# ── GUI ───────────────────────────────────────────────────────────────────────

def _is_model_top_window(text: str) -> bool:
    """La ventana principal del modelo NO tiene '/' en el título (las ventanas
    de subsistemas y scopes sí, p.ej. 'Modelo/Mitigation' o 'Modelo/C. Circul',
    incluso si no contienen la palabra 'Scope'). Puede tener sufijos como
    ' *' (cambios sin guardar) y ' [running]'."""
    if "/" in text:
        return False
    base = text.split(" *")[0].split(" [running]")[0].strip()
    return base == MODEL_NAME


def _forzar_foreground(hwnd: int):
    """win.set_focus() de pywinauto (UIA) a veces reporta éxito sin realmente
    traer la ventana al frente del z-order de Windows (visto en producción:
    PLECS queda detrás de VSCode/terminal, Ctrl+T no llega a ningún lado).
    Windows restringe SetForegroundWindow para procesos en segundo plano
    (foreground lock) — un intento directo suele fallar con "Acceso
    denegado" o quedar sin efecto. AttachThreadInput vincula temporalmente
    el hilo de este proceso con el de la ventana que SÍ tiene el foco,
    lo cual generalmente evita esa restricción."""
    hwnd_actual = win32gui.GetForegroundWindow()
    if hwnd_actual == hwnd:
        return

    tid_actual, _ = win32process.GetWindowThreadProcessId(hwnd_actual) if hwnd_actual else (0, 0)
    tid_destino, _ = win32process.GetWindowThreadProcessId(hwnd)
    tid_propio = win32api.GetCurrentThreadId()

    adjuntado_actual = False
    adjuntado_propio = False
    try:
        if tid_actual and tid_actual != tid_destino:
            win32process.AttachThreadInput(tid_actual, tid_destino, True)
            adjuntado_actual = True
        if tid_propio != tid_destino:
            win32process.AttachThreadInput(tid_propio, tid_destino, True)
            adjuntado_propio = True

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    finally:
        if adjuntado_actual:
            win32process.AttachThreadInput(tid_actual, tid_destino, False)
        if adjuntado_propio:
            win32process.AttachThreadInput(tid_propio, tid_destino, False)


def _focus_model_win():
    wins = [w for w in Desktop(backend="uia").windows()
            if _is_model_top_window(w.window_text())]
    if not wins:
        raise RuntimeError("Ventana del modelo PLECS no encontrada.")
    if len(wins) > 1:
        raise RuntimeError(
            f"Se encontró más de una ventana principal candidata: "
            f"{[w.window_text() for w in wins]}"
        )
    win = wins[0]
    win.set_focus()
    time.sleep(0.2)

    hwnd = win.handle
    if win32gui.GetForegroundWindow() != hwnd:
        _forzar_foreground(hwnd)
        time.sleep(0.3)

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(
            "No se pudo traer la ventana del modelo PLECS al primer plano "
            "(set_focus de pywinauto no es suficiente en este sistema)."
        )
    time.sleep(0.2)


def _is_running() -> bool:
    return any(_is_model_top_window(w.window_text()) and "[running]" in w.window_text()
               for w in Desktop(backend="uia").windows())


def _stop_simulation():
    if not _is_running():
        return
    _focus_model_win()
    pyautogui.hotkey("ctrl", "t")
    deadline = time.time() + 20.0
    while time.time() < deadline:
        time.sleep(0.5)
        if not _is_running():
            return
    raise RuntimeError("No se pudo detener la simulación en 20s.")


def run_simulation(timeout: float = 120.0):
    """Inicia simulación y espera a que termine.

    Si el solver diverge (NaN/Inf), PLECS puede quedarse colgado en estado
    [running] indefinidamente en vez de terminar con error. Por eso, al llegar
    al timeout, se fuerza la detención (Ctrl+T) y se levanta TimeoutError en
    vez de devolver silenciosamente con la simulación todavía corriendo.
    """
    _stop_simulation()
    time.sleep(0.2)
    _focus_model_win()
    pyautogui.hotkey("ctrl", "t")

    # Ventana de carrera: si la simulación es muy corta (p.ej. T_SIM chico o
    # convergencia/crash casi inmediato), puede arrancar Y terminar antes de
    # que el primer chequeo de _is_running() la detecte. Por eso se chequea
    # inmediatamente (sin sleep previo) y con polling denso al inicio.
    detectada_corriendo = False
    deadline_start = time.time() + 10.0
    while time.time() < deadline_start:
        if _is_running():
            detectada_corriendo = True
            break
        time.sleep(0.05)

    if not detectada_corriendo:
        # Pudo haber corrido y terminado completo entre el Ctrl+T y el primer
        # chequeo (polling de 50ms no es infalible). No asumir que no corrió:
        # seguir al chequeo de "terminó" normalmente; si en verdad nunca
        # arrancó, el caller validará contra datos (p.ej. export vacío).
        time.sleep(0.5)
        return

    deadline_end = time.time() + timeout
    while time.time() < deadline_end:
        if not _is_running():
            time.sleep(1.5)
            return
        time.sleep(0.3)

    # Timeout: forzar detención (probable divergencia NaN/Inf del solver).
    try:
        _stop_simulation()
    except Exception:
        pass
    raise TimeoutError(
        f"La simulación no terminó en {timeout}s (posible divergencia del solver)."
    )


# ── Exportar scopes ───────────────────────────────────────────────────────────

def verificar_scopes_abiertos():
    """Chequea que las ventanas de todos los SCOPES configurados estén abiertas
    AHORA, antes de intentar exportar. Falla con un mensaje claro indicando
    cuál falta, en vez de colgarse silenciosamente en pywinauto (visto en
    producción: si una ventana de scope se cierra o nunca se abrió, el export
    queda esperando indefinidamente sin traceback útil)."""
    titulos_abiertos = {w.window_text() for w in Desktop(backend="uia").windows()}
    faltantes = [key for key, title in SCOPES.items() if title not in titulos_abiertos]
    if faltantes:
        raise RuntimeError(
            f"Las siguientes ventanas de scope no están abiertas en PLECS: "
            f"{[SCOPES[k] for k in faltantes]}. Abrilas manualmente antes de simular."
        )


def export_scope_csv(scope_key: str, csv_path: Path, intentos: int = 3):
    """Exporta el scope indicado a CSV. scope_key debe estar en SCOPES.

    Reintenta el flujo completo si falla abrir File > Export (visto en
    producción: PLECS a veces devuelve el foco a la ventana principal del
    modelo justo después de set_focus(), antes de poder hacer clic en el
    menú). NOTA: Desktop(backend="uia").window(active_only=True) es poco
    fiable en este sistema (tarda ~5s y lanza excepción en vez de detectar
    la ventana activa correctamente) — NO usar para verificar foco; en su
    lugar, reintentar el flujo completo directamente si click_input falla."""
    scope_title = SCOPES[scope_key]
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            app = Application(backend="uia").connect(title=scope_title)
            win = app.window(title=scope_title)
            win.set_focus()
            time.sleep(0.2)
            # win.set_focus() de pywinauto no siempre gana el foco real de
            # Windows (foreground lock) — forzarlo explícitamente, igual que
            # en _focus_model_win().
            if win32gui.GetForegroundWindow() != win.handle:
                _forzar_foreground(win.handle)
                time.sleep(0.3)

            win.child_window(title="File", control_type="MenuItem").click_input()
            time.sleep(0.3)
            win.child_window(title="Export", control_type="MenuItem").click_input()
            time.sleep(0.3)
            break
        except Exception as e:
            ultimo_error = e
            if intento < intentos:
                time.sleep(0.5 * intento)
                continue
            raise RuntimeError(
                f"No se pudo abrir File > Export en el scope {scope_title!r} tras "
                f"{intentos} intentos. Último error: {ultimo_error}"
            )

    csv_item = win.child_window(title="as CSV", control_type="MenuItem")
    rect = csv_item.rectangle()
    pyautogui.moveTo((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    time.sleep(0.3)

    # Buscar "All..." en submenú
    all_item = None
    for w in Desktop(backend="uia").windows():
        try:
            for item in w.descendants(control_type="MenuItem"):
                if "All" in item.window_text():
                    all_item = item
                    break
        except Exception:
            pass
        if all_item:
            break

    if not all_item:
        raise RuntimeError(f"No se encontró 'All...' para scope '{scope_key}'.")

    r = all_item.rectangle()
    pyautogui.click((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    time.sleep(1.0)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.typewrite(str(csv_path), interval=0.02)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.8)
    pyautogui.press("left")
    time.sleep(0.15)
    pyautogui.press("enter")

    _wait_for_file_stable(csv_path, timeout=30.0)


def _wait_for_file_stable(path: Path, timeout: float = 30.0, poll: float = 0.3, stable_checks: int = 3):
    """Espera a que el archivo exista y su tamaño deje de crecer (export async de PLECS)."""
    deadline = time.time() + timeout
    last_size = -1
    stable_count = 0
    while time.time() < deadline:
        if path.exists():
            size = path.stat().st_size
            if size > 0 and size == last_size:
                stable_count += 1
                if stable_count >= stable_checks:
                    return
            else:
                stable_count = 0
            last_size = size
        time.sleep(poll)
    if not path.exists():
        raise RuntimeError(f"CSV no generado: {path}")
    raise RuntimeError(f"CSV no terminó de escribirse en {timeout}s: {path}")


def read_scope_csv(csv_path: Path) -> pd.DataFrame:
    """Lee CSV exportado por PLECS. Retorna DataFrame con columnas numéricas."""
    df = pd.read_csv(csv_path, header=None, comment="%")
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    df.columns = [f"col{i}" for i in range(df.shape[1])]
    df = df.rename(columns={"col0": "time"})
    return df
