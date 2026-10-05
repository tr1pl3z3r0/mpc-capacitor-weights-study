"""
data_logger.py — Guardar CSV log, datos de scopes e imágenes.
"""

import csv
import os
import shutil
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"
LOG_FILE    = RESULTS_DIR / "log.csv"
IMAGES_DIR  = RESULTS_DIR / "images"


def init_log(columns: list):
    """Crea log.csv con los headers indicados. Borra el anterior si existe."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["eval", "timestamp"] + columns)


def append_log(eval_id: int, data: dict):
    """Agrega una fila al log. data debe tener las mismas keys que columns en init_log."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    row = {"eval": eval_id, "timestamp": datetime.now().isoformat(timespec="seconds"), **data}
    with open(LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=list(row.keys())).writerow(row)


def read_log() -> pd.DataFrame:
    """Lee el log actual como DataFrame."""
    return pd.read_csv(LOG_FILE)


def save_scope_data(eval_id: int, scope_key: str, df: pd.DataFrame):
    """Guarda los datos crudos de un scope como CSV por evaluación."""
    out_dir = RESULTS_DIR / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval{eval_id:04d}_{scope_key}.csv"
    df.to_csv(path, index=False)
    return path


def save_scope_image(eval_id: int, scope_key: str, df: pd.DataFrame,
                     y_cols: list = None, title: str = None, ylabel: str = ""):
    """Genera y guarda imagen PNG de las señales del scope."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / f"eval{eval_id:04d}_{scope_key}.png"

    if y_cols is None:
        y_cols = [c for c in df.columns if c != "time"]

    fig, ax = plt.subplots(figsize=(10, 4))
    for col in y_cols:
        ax.plot(df["time"], df[col], label=col)
    ax.set_xlabel("Tiempo [s]")
    ax.set_ylabel(ylabel)
    ax.set_title(title or f"eval {eval_id} — {scope_key}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def copy_scope_csv(src: Path, eval_id: int, scope_key: str) -> Path:
    """Copia un CSV exportado de PLECS al directorio raw con nombre por evaluación."""
    out_dir = RESULTS_DIR / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"eval{eval_id:04d}_{scope_key}.csv"
    shutil.copy2(src, dst)
    return dst
