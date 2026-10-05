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
from pywinauto import Desktop, Application

# ── Configuración ─────────────────────────────────────────────────────────────
MODEL_NAME = "MMC_sinmodulacion - Con MPC - Corrección Predicciones"          # nombre exacto del modelo en PLECS
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
    """
    _stop_simulation()

    pesos_redondeados = {k: _redondear_3_cifras(v) for k, v in pesos.items()}

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
    wins[0].set_focus()
    time.sleep(0.4)


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

    deadline_start = time.time() + 10.0
    while time.time() < deadline_start:
        if _is_running():
            break
        time.sleep(0.2)

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

def export_scope_csv(scope_key: str, csv_path: Path):
    """Exporta el scope indicado a CSV. scope_key debe estar en SCOPES."""
    scope_title = SCOPES[scope_key]
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    app = Application(backend="uia").connect(title=scope_title)
    win = app.window(title=scope_title)
    win.set_focus()
    time.sleep(0.3)

    win.child_window(title="File", control_type="MenuItem").click_input()
    time.sleep(0.3)
    win.child_window(title="Export", control_type="MenuItem").click_input()
    time.sleep(0.3)

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
