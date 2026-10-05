"""
simulador.py — Módulo central: corre un punto de diseño en PLECS, exporta los
3 scopes, calcula todas las métricas (ver metricas.py) y escribe una fila en
simulaciones.csv (esquema de INSTRUCCIONES.md sección 8).

Los 3 CSV crudos exportados de PLECS + la fila de métricas de cada simulación
se guardan en resultados/raw/sim{id:05d}/ (local, NO se sube a git — ver
git_sync.py y .gitignore). Solo simulaciones.csv se versiona.

Uso típico:
    from simulador import simular_punto
    fila = simular_punto(horizonte=3, pesos={...}, fase="fase1", semilla=42)

Para ejecución multi-máquina coordinada vía GitHub, usar usar_git=True (ver
git_sync.py para el mecanismo de claim).
"""

import csv
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import config
import metricas
import plecs_runner as pr

pr.MODEL_NAME = config.MODEL_NAME
pr.SCOPES = config.SCOPES

COLUMNAS_CSV = [
    "id", "fecha_hora", "fase", "horizonte", "maquina_id",
    "q11", "q22", "q33", "q44", "q55", "r11", "r22", "Q_Val", "R_Val", "T_SIM",
    "estado",
    "osc_vcap_ap", "osc_vcap_bp", "osc_vcap_cp", "osc_vcap_an", "osc_vcap_bn", "osc_vcap_cn",
    "osc_max", "desv_max",
    "media_vcap_ap", "media_vcap_bp", "media_vcap_cp", "media_vcap_an", "media_vcap_bn", "media_vcap_cn",
    "rms_icirc_alpha", "rms_icirc_beta", "rms_icirc_peor", "rms_icirc_T025",
    "max_icirc", "min_icirc", "pico_abs_icirc",
    "rmse_vcap", "itae",
    "idc_abs_max",
    "valida_P0", "cumple_P1", "duracion_s", "semilla",
]

VCAP_NOMBRES = ["ap", "bp", "cp", "an", "bn", "cn"]


def _proximo_id() -> int:
    if not config.CSV_SIMULACIONES.exists():
        return 1
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    if not filas:
        return 1
    return max(int(r["id"]) for r in filas) + 1


def init_csv():
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    if not config.CSV_SIMULACIONES.exists():
        with open(config.CSV_SIMULACIONES, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNAS_CSV).writeheader()


def _append_csv(fila: dict):
    """Agrega una fila nueva, o REEMPLAZA la fila existente con el mismo id si
    ya estaba (caso: pasar de CORRIENDO al resultado final en flujo con git)."""
    init_csv()
    filas = _leer_filas_crudas()
    reemplazada = False
    for i, row in enumerate(filas):
        if row["id"] == str(fila["id"]):
            filas[i] = fila
            reemplazada = True
            break
    if not reemplazada:
        filas.append(fila)

    with open(config.CSV_SIMULACIONES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
        w.writeheader()
        for row in filas:
            w.writerow(row)
        f.flush()


def _leer_filas_crudas() -> list:
    if not config.CSV_SIMULACIONES.exists():
        return []
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def buscar_existente(horizonte: int, pesos_redondeados: dict) -> dict | None:
    """Sección 8: antes de simular, reutilizar si la combinación exacta (horizonte +
    pesos redondeados) ya está en el CSV."""
    for row in _leer_filas_crudas():
        if int(row["horizonte"]) != horizonte:
            continue
        if all(abs(float(row[k]) - v) < 1e-12 for k, v in pesos_redondeados.items()):
            return row
    return None


def _carpeta_sim(sim_id: int) -> Path:
    return config.RESULTADOS_DIR / "raw" / f"sim{sim_id:05d}"


def _cargar_scopes(carpeta: Path):
    """Exporta los 3 scopes directamente a resultados/raw/sim{id}/{key}.csv."""
    carpeta.mkdir(parents=True, exist_ok=True)
    dfs = {}
    for key in config.SCOPES:
        csv_path = carpeta / f"{key}.csv"
        pr.export_scope_csv(key, csv_path)
        dfs[key] = pr.read_scope_csv(csv_path)
    return dfs


def _peor_senal_icirc(t, col_alpha, col_beta, t_ini, t_fin):
    rms_a = metricas.rms(t, col_alpha, t_ini, t_fin)
    rms_b = metricas.rms(t, col_beta, t_ini, t_fin)
    return (col_alpha, rms_a) if rms_a >= rms_b else (col_beta, rms_b)


def simular_punto(horizonte: int, pesos: dict, fase: str, semilla: int = None,
                   reusar_si_existe: bool = True, usar_git: bool = False) -> dict:
    """Corre (o reutiliza) un punto de diseño completo y devuelve la fila escrita
    (o reutilizada) en simulaciones.csv como dict.

    Si usar_git=True, coordina con otras máquinas vía GitHub (ver git_sync.py):
    hace pull, reclama el punto con una fila CORRIENDO + push inmediato, y al
    terminar sincroniza el resultado final. Si el punto ya fue tomado por otra
    máquina, devuelve None (el llamador debe pedir un punto distinto).
    """
    t0 = time.time()
    semilla = semilla if semilla is not None else config.SEMILLA

    pesos_redondeados = {k: pr._redondear_3_cifras(v) for k, v in pesos.items()}

    if usar_git:
        import git_sync
        git_sync.pull()

    if reusar_si_existe:
        existente = buscar_existente(horizonte, pesos_redondeados)
        if existente is not None and existente["estado"] != "CORRIENDO":
            return existente

    if usar_git:
        import git_sync
        if not git_sync.punto_libre(horizonte, pesos_redondeados):
            return None  # otra máquina ya lo tomó o lo terminó

    sim_id = _proximo_id()
    carpeta = _carpeta_sim(sim_id)

    fila_base = {
        "id": sim_id,
        "fecha_hora": datetime.now().isoformat(timespec="seconds"),
        "fase": fase,
        "horizonte": horizonte,
        "maquina_id": config.MAQUINA_ID,
        **pesos_redondeados,
        "Q_Val": config.Q_VAL,
        "R_Val": config.R_VAL,
        "T_SIM": config.T_SIM,
        "semilla": semilla,
    }

    if usar_git:
        import git_sync
        fila_claim = {**fila_base, "estado": "CORRIENDO", "valida_P0": "", "cumple_P1": "",
                      "duracion_s": ""}
        for col in COLUMNAS_CSV:
            fila_claim.setdefault(col, "")
        if not git_sync.reclamar_punto(fila_claim):
            return None  # conflicto persistente, el llamador debe pedir otro punto

    try:
        pr.aplicar_punto(horizonte, pesos, config)
        pr.run_simulation(timeout=config.TIMEOUT_SIM)
    except Exception as e:
        fila = {**fila_base, "estado": "FALLIDA", "valida_P0": False, "cumple_P1": False,
                "duracion_s": round(time.time() - t0, 2)}
        for col in COLUMNAS_CSV:
            fila.setdefault(col, "")
        _append_csv(fila)
        if usar_git:
            import git_sync
            git_sync.sincronizar_resultado_final(f"sim {sim_id}: FALLIDA")
        return fila

    try:
        dfs = _cargar_scopes(carpeta)
    except Exception as e:
        fila = {**fila_base, "estado": "TIMEOUT", "valida_P0": False, "cumple_P1": False,
                "duracion_s": round(time.time() - t0, 2)}
        for col in COLUMNAS_CSV:
            fila.setdefault(col, "")
        _append_csv(fila)
        if usar_git:
            import git_sync
            git_sync.sincronizar_resultado_final(f"sim {sim_id}: TIMEOUT (export)")
        return fila

    vcap_df = dfs["v_cap"]
    icirc_df = dfs["i_circ"]
    idc_df = dfs["i_dc"]

    t_vcap = vcap_df["time"].to_numpy()
    t_icirc = icirc_df["time"].to_numpy()
    t_idc = idc_df["time"].to_numpy()

    t_sim_real = config.T_SIM
    t_ini_ventana = t_sim_real - config.T_VENTANA
    t_fin_ventana = t_sim_real

    # NaN/Inf check (P0.a)
    arrays_a_chequear = (
        [vcap_df[c].to_numpy() for c in vcap_df.columns if c != "time"]
        + [icirc_df[c].to_numpy() for c in icirc_df.columns if c != "time"]
        + [idc_df[c].to_numpy() for c in idc_df.columns if c != "time"]
    )
    tiene_nan_inf = any(not np.all(np.isfinite(a)) for a in arrays_a_chequear)

    if tiene_nan_inf:
        fila = {**fila_base, "estado": "INVALIDA", "valida_P0": False, "cumple_P1": False,
                "duracion_s": round(time.time() - t0, 2)}
        for col in COLUMNAS_CSV:
            fila.setdefault(col, "")
        _append_csv(fila)
        if usar_git:
            import git_sync
            git_sync.sincronizar_resultado_final(f"sim {sim_id}: INVALIDA (NaN/Inf)")
        return fila

    vcap_cols = [c for c in vcap_df.columns if c != "time"]
    senales_vcap = [vcap_df[c].to_numpy() for c in vcap_cols]

    osc_por_cap = [metricas.pico_pico(t_vcap, v, t_ini_ventana, t_fin_ventana) for v in senales_vcap]
    osc_max = max(osc_por_cap)
    desv_max = max(metricas.desviacion_max(t_vcap, v, t_ini_ventana, t_fin_ventana, config.V_REF)
                    for v in senales_vcap)
    medias = [metricas.media_ventana(t_vcap, v, t_ini_ventana, t_fin_ventana) for v in senales_vcap]

    rms_alpha = metricas.rms(t_icirc, icirc_df["col1"].to_numpy(), t_ini_ventana, t_fin_ventana)
    rms_beta = metricas.rms(t_icirc, icirc_df["col2"].to_numpy(), t_ini_ventana, t_fin_ventana)
    peor_senal, rms_peor = _peor_senal_icirc(
        t_icirc, icirc_df["col1"].to_numpy(), icirc_df["col2"].to_numpy(), t_ini_ventana, t_fin_ventana
    )

    t_ini_t025 = t_sim_real - 0.25
    rms_t025 = metricas.rms(t_icirc, peor_senal, t_ini_t025, t_sim_real)

    max_icirc = float(peor_senal[(t_icirc >= t_ini_ventana) & (t_icirc <= t_fin_ventana)].max())
    min_icirc = float(peor_senal[(t_icirc >= t_ini_ventana) & (t_icirc <= t_fin_ventana)].min())
    pico_abs_icirc = max(abs(max_icirc), abs(min_icirc))

    rmse_vcap = max(metricas.rmse_respecto_ref(t_vcap, v, t_ini_ventana, t_fin_ventana, config.V_REF)
                     for v in senales_vcap)
    itae = max(metricas.itae(t_vcap, v, config.V_REF, 0.0, t_sim_real) for v in senales_vcap)

    idc_col = idc_df["col1"].to_numpy()
    _, idc_win = metricas.recortar_ventana(t_idc, idc_col, t_ini_ventana, t_fin_ventana)
    idc_abs_max = float(np.max(np.abs(idc_win)))

    regimen = metricas.regimen_permanente(t_vcap, senales_vcap, peor_senal, t_sim_real)

    valida_media = all(abs(m - config.V_REF) <= config.TOL_V_MEDIA for m in medias)
    valida_idc = idc_abs_max <= config.TOL_I_DC
    valida_P0 = regimen["estacionario"] and valida_media and valida_idc
    cumple_P1 = osc_max < config.OSC_MAX

    estado = "OK" if valida_P0 else "NO_ESTACIONARIO"

    fila = {
        **fila_base,
        "estado": estado,
        **{f"osc_vcap_{n}": round(o, 4) for n, o in zip(VCAP_NOMBRES, osc_por_cap)},
        "osc_max": round(osc_max, 4),
        "desv_max": round(desv_max, 4),
        **{f"media_vcap_{n}": round(m, 4) for n, m in zip(VCAP_NOMBRES, medias)},
        "rms_icirc_alpha": round(rms_alpha, 4),
        "rms_icirc_beta": round(rms_beta, 4),
        "rms_icirc_peor": round(rms_peor, 4),
        "rms_icirc_T025": round(rms_t025, 4),
        "max_icirc": round(max_icirc, 4),
        "min_icirc": round(min_icirc, 4),
        "pico_abs_icirc": round(pico_abs_icirc, 4),
        "rmse_vcap": round(rmse_vcap, 4),
        "itae": round(itae, 4),
        "idc_abs_max": round(idc_abs_max, 6),
        "valida_P0": valida_P0,
        "cumple_P1": cumple_P1,
        "duracion_s": round(time.time() - t0, 2),
    }

    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "metricas.json", "w", encoding="utf-8") as f:
        json.dump(fila, f, indent=2, ensure_ascii=False)

    _append_csv(fila)
    if usar_git:
        import git_sync
        git_sync.sincronizar_resultado_final(f"sim {sim_id}: {estado} (horizonte={horizonte})")
    return fila
