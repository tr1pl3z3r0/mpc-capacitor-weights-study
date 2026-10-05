"""
fase5_figuras.py — Genera las figuras PNG de la sección 7, Fase 5, en
resultados/figuras/:
  1. Sensibilidad de cada peso (de fase2_sensibilidad.py).
  2. Por horizonte: dispersión RMS i_circ vs osc, línea en 10V, seleccionados
     resaltados.
  3. Mejor RMS factible (y su osc) vs horizonte.
  4. Formas de onda (v_cap, i_circ) del caso base y del mejor conjunto de
     cada horizonte, leídas de resultados/raw/sim{id}/ LOCAL (no se
     sincroniza vía git; si el sim_id fue corrido por otra máquina, se
     reporta como pendiente en esta máquina).

Uso:
    python fase5_figuras.py
"""

import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

PALETA = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
          "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC", "#EECA3B"]


def _to_float(row: dict, key: str, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _leer_csv_sim() -> list:
    with open(config.CSV_SIMULACIONES, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig_sensibilidad():
    path = config.RESULTADOS_DIR / "fase2_conclusiones.json"
    if not path.exists():
        print("  (sin fase2_conclusiones.json, se omite figura de sensibilidad)")
        return

    filas = _leer_csv_sim()
    filas_fase2 = [r for r in filas if r["fase"] == "fase2"]

    for peso in config.NOMBRES_PESOS:
        puntos = []
        for r in filas_fase2:
            val = _to_float(r, peso)
            base_val = config.PESOS_BASE[peso]
            if val is None or val <= 0:
                continue
            exp = np.log10(val / base_val)
            if abs(exp - round(exp)) > 0.05:
                continue  # no es un punto del barrido de ese peso (otro peso varió)
            otros_en_base = all(
                abs(_to_float(r, p, -1) - config.PESOS_BASE[p]) < 1e-9
                for p in config.NOMBRES_PESOS if p != peso
            )
            if not otros_en_base:
                continue
            if r["estado"] != "OK":
                continue
            puntos.append((exp, _to_float(r, "osc_max"), _to_float(r, "rms_icirc_peor"),
                            _to_float(r, "pico_abs_icirc")))

        if not puntos:
            continue
        puntos.sort(key=lambda p: p[0])
        exps, oscs, rmss, picos = zip(*puntos)

        fig, axes = plt.subplots(1, 3, figsize=(13, 4))
        for ax, vals, titulo, color in zip(
            axes, [oscs, rmss, picos],
            ["Oscilación (V)", "RMS i_circ (A)", "Pico abs i_circ (A)"],
            PALETA[:3],
        ):
            ax.plot(exps, vals, "o-", color=color)
            ax.set_xlabel(f"log10({peso} / base)")
            ax.set_title(titulo)
            ax.grid(True, alpha=0.3)
        fig.suptitle(f"Sensibilidad: {peso} (N={config.HORIZONTE_REFERENCIA})")
        fig.tight_layout()
        out = config.FIGURAS_DIR / f"sensibilidad_{peso}.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"  {out}")


def fig_dispersión_por_horizonte(seleccion: dict):
    filas = _leer_csv_sim()

    for h_str, bloque in seleccion.items():
        h = int(h_str)
        filas_h = [r for r in filas if int(r["horizonte"]) == h and r["estado"] == "OK"]
        if not filas_h:
            continue

        oscs = [_to_float(r, "osc_max") for r in filas_h]
        rmss = [_to_float(r, "rms_icirc_peor") for r in filas_h]
        ids = [r["id"] for r in filas_h]

        seleccionados_ids = {p["id"] for p in bloque["pruebas_2_a_10"]}

        fig, ax = plt.subplots(figsize=(7, 5))
        colores = [PALETA[2] if i in seleccionados_ids else PALETA[8] for i in ids]
        ax.scatter(oscs, rmss, c=colores, alpha=0.7, edgecolors="none")
        ax.axvline(config.OSC_MAX, color=PALETA[3], linestyle="--", label=f"{config.OSC_MAX} V")
        ax.set_xlabel("Oscilación capacitores (V)")
        ax.set_ylabel("RMS corriente circulante (A)")
        ax.set_title(f"Horizonte N={h}: RMS vs oscilación")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        out = config.FIGURAS_DIR / f"dispersion_horizonte_{h}.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        print(f"  {out}")


def fig_mejor_rms_vs_horizonte(seleccion: dict):
    horizontes = []
    mejores_rms = []
    mejores_osc = []

    for h_str, bloque in sorted(seleccion.items(), key=lambda kv: int(kv[0])):
        no_cumple = set(bloque.get("no_cumple_ids", []))
        candidatos = [p for p in bloque["pruebas_2_a_10"] if p["id"] not in no_cumple]
        if not candidatos:
            continue
        mejor = candidatos[0]
        horizontes.append(int(h_str))
        mejores_rms.append(_to_float(mejor, "rms_icirc_peor"))
        mejores_osc.append(_to_float(mejor, "osc_max"))

    if not horizontes:
        print("  (sin candidatos factibles en ningún horizonte, se omite figura)")
        return

    fig, ax1 = plt.subplots(figsize=(7, 5))
    ax1.plot(horizontes, mejores_rms, "o-", color=PALETA[0], label="RMS i_circ (A)")
    ax1.set_xlabel("Horizonte N")
    ax1.set_ylabel("Mejor RMS i_circ factible (A)", color=PALETA[0])
    ax1.tick_params(axis="y", labelcolor=PALETA[0])

    ax2 = ax1.twinx()
    ax2.plot(horizontes, mejores_osc, "s--", color=PALETA[1], label="Oscilación (V)")
    ax2.set_ylabel("Oscilación del mejor punto (V)", color=PALETA[1])
    ax2.tick_params(axis="y", labelcolor=PALETA[1])

    ax1.set_title("Mejor RMS factible y su oscilación vs horizonte")
    ax1.grid(True, alpha=0.3)
    fig.tight_layout()
    out = config.FIGURAS_DIR / "mejor_rms_vs_horizonte.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  {out}")


def _leer_scope_local(sim_id, key) -> pd.DataFrame:
    path = config.RESULTADOS_DIR / "raw" / f"sim{int(sim_id):05d}" / f"{key}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, header=None, comment="%")
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    df.columns = [f"col{i}" for i in range(df.shape[1])]
    df = df.rename(columns={"col0": "time"})
    return df


def fig_formas_de_onda(seleccion: dict):
    nombres_vcap = ["ap", "bp", "cp", "an", "bn", "cn"]

    for h_str, bloque in seleccion.items():
        h = int(h_str)
        casos = [("caso_base", bloque["prueba_1_caso_base"])]
        no_cumple = set(bloque.get("no_cumple_ids", []))
        candidatos = [p for p in bloque["pruebas_2_a_10"] if p["id"] not in no_cumple]
        if candidatos:
            casos.append(("mejor", candidatos[0]))

        for etiqueta, prueba in casos:
            sim_id = prueba.get("id")
            if sim_id in (None, ""):
                continue

            df_vcap = _leer_scope_local(sim_id, "v_cap")
            df_icirc = _leer_scope_local(sim_id, "i_circ")
            if df_vcap is None or df_icirc is None:
                print(f"  (horizonte {h}, {etiqueta}: sim {sim_id} sin datos crudos locales, "
                      f"omitido — probablemente corrida en otra máquina)")
                continue

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
            for j, nombre in enumerate(nombres_vcap):
                col = f"col{j+1}"
                if col in df_vcap.columns:
                    ax1.plot(df_vcap["time"], df_vcap[col], label=f"v_cap_{nombre}",
                              color=PALETA[j % len(PALETA)])
            ax1.axhline(config.V_REF, color="gray", linestyle=":", alpha=0.6)
            ax1.set_ylabel("Voltaje capacitor (V)")
            ax1.legend(ncol=3, fontsize=8)
            ax1.grid(True, alpha=0.3)

            for j, nombre in enumerate(["alpha", "beta"]):
                col = f"col{j+1}"
                if col in df_icirc.columns:
                    ax2.plot(df_icirc["time"], df_icirc[col], label=f"i_circ_{nombre}",
                              color=PALETA[j])
            ax2.set_xlabel("Tiempo (s)")
            ax2.set_ylabel("Corriente circulante (A)")
            ax2.legend(fontsize=8)
            ax2.grid(True, alpha=0.3)

            fig.suptitle(f"Horizonte N={h} — {etiqueta} (sim {sim_id})")
            fig.tight_layout()
            out = config.FIGURAS_DIR / f"formas_onda_h{h}_{etiqueta}.png"
            fig.savefig(out, dpi=120)
            plt.close(fig)
            print(f"  {out}")


def main():
    seleccion_path = config.RESULTADOS_DIR / "fase4_seleccion.json"
    if not seleccion_path.exists():
        raise RuntimeError(f"No existe {seleccion_path}; correr fase4_seleccion.py primero.")
    with open(seleccion_path, "r", encoding="utf-8") as f:
        seleccion = json.load(f)

    config.FIGURAS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Fase 5: generando figuras")
    print("=" * 60)

    print("\n[1/4] Sensibilidad por peso...")
    fig_sensibilidad()

    print("\n[2/4] Dispersión RMS vs osc por horizonte...")
    fig_dispersión_por_horizonte(seleccion)

    print("\n[3/4] Mejor RMS vs horizonte...")
    fig_mejor_rms_vs_horizonte(seleccion)

    print("\n[4/4] Formas de onda (caso base y mejor por horizonte)...")
    fig_formas_de_onda(seleccion)

    print(f"\nFiguras guardadas en {config.FIGURAS_DIR}")
    print("Fase 5 (figuras) completa.")


if __name__ == "__main__":
    main()
