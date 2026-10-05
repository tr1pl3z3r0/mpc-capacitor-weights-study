"""
experimentos.py — Script de pruebas. Editá PUNTOS y COLUMNS según tu modelo.

Uso:
    python experimentos.py
"""

from pathlib import Path
from plecs_runner import set_params, run_simulation, export_scope_csv, read_scope_csv
from data_logger import init_log, append_log, save_scope_image, copy_scope_csv

# ── Carpeta temporal para CSVs exportados por PLECS ───────────────────────────
TMP = Path("results/tmp")
TMP.mkdir(parents=True, exist_ok=True)

# ── Columnas del log (nombres de tus métricas) ────────────────────────────────
COLUMNS = ["param_a", "param_b", "ss_sig1", "ss_sig2", "ss_v0s"]

# ── Puntos a probar ───────────────────────────────────────────────────────────
# (label, param_a, param_b)
PUNTOS = [
    ("punto1", 1.0, 10.0),
    ("punto2", 2.0, 10.0),
    ("punto3", 3.0, 10.0),
]


def procesar_scope1(df):
    """Extrae métricas de las columnas del scope1. Ajustá los índices a tu modelo."""
    sig1 = df["col1"].to_numpy()  # columna 1 = señal 1
    sig2 = df["col2"].to_numpy()  # columna 2 = señal 2
    tail = max(1, int(len(sig1) * 0.1))
    return {
        "ss_sig1": float(sig1[-tail:].mean()),
        "ss_sig2": float(sig2[-tail:].mean()),
    }


def procesar_scope2(df):
    """Extrae métricas del scope2."""
    v0s  = df["col1"].to_numpy()
    tail = max(1, int(len(v0s) * 0.1))
    return {"ss_v0s": float(v0s[-tail:].mean())}


def main():
    init_log(COLUMNS)
    print(f"{'='*60}")
    print("  Experimentos MMC")
    print(f"{'='*60}\n")

    for eval_id, (label, a, b) in enumerate(PUNTOS, start=1):
        print(f"[{eval_id}] {label}  a={a}  b={b}")
        try:
            # 1. Setear parámetros y correr
            set_params({"a": a, "b": b})
            run_simulation()

            # 2. Exportar scopes a CSV temporal
            csv1 = TMP / f"scope1_{eval_id}.csv"
            csv2 = TMP / f"scope2_{eval_id}.csv"
            export_scope_csv("scope1", csv1)
            export_scope_csv("scope2", csv2)

            # 3. Leer datos
            df1 = read_scope_csv(csv1)
            df2 = read_scope_csv(csv2)

            # 4. Calcular métricas
            m1 = procesar_scope1(df1)
            m2 = procesar_scope2(df2)

            # 5. Guardar imagen
            save_scope_image(eval_id, "scope1", df1,
                             y_cols=["col1", "col2"], ylabel="Amplitud")
            save_scope_image(eval_id, "scope2", df2,
                             y_cols=["col1"], ylabel="V0Σ [V]")

            # 6. Loguear
            row = {"param_a": a, "param_b": b, **m1, **m2}
            append_log(eval_id, row)

            print(f"  ss_sig1={m1['ss_sig1']:.3f}  ss_sig2={m1['ss_sig2']:.3f}"
                  f"  ss_v0s={m2['ss_v0s']:.3f}")

        except Exception as ex:
            print(f"  ERROR: {ex}")
            append_log(eval_id, {"param_a": a, "param_b": b,
                                  "ss_sig1": None, "ss_sig2": None, "ss_v0s": None})

    print(f"\n{'='*60}")
    print("  Listo. Resultados en results/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
