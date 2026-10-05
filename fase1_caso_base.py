"""
fase1_caso_base.py — Simula PESOS_BASE en cada uno de los HORIZONTES.
Este caso es la Prueba 1 de cada bloque en el Excel final (sección 7, Fase 1).

Uso:
    python fase1_caso_base.py              # solo esta máquina, sin coordinar
    python fase1_caso_base.py --git         # coordina con otras máquinas vía GitHub
"""

import sys

import config
from simulador import simular_punto


def main():
    usar_git = "--git" in sys.argv

    print("=" * 60)
    print(f"  Fase 1: caso base en cada horizonte (maquina={config.MAQUINA_ID}, git={usar_git})")
    print("=" * 60)

    for h in config.HORIZONTES:
        print(f"\n[Horizonte N={h}] simulando caso base...")
        fila = simular_punto(horizonte=h, pesos=config.PESOS_BASE, fase="fase1", usar_git=usar_git)
        if fila is None:
            print("  (ya tomado/terminado por otra máquina, se omite)")
            continue
        estado = fila["estado"]
        osc = fila.get("osc_max", "")
        rms = fila.get("rms_icirc_peor", "")
        print(f"  id={fila['id']}  estado={estado}  osc_max={osc}  rms_icirc_peor={rms}  "
              f"duracion={fila['duracion_s']}s")

    print("\nFase 1 completa. Ver resultados/simulaciones.csv (fase=fase1).")


if __name__ == "__main__":
    main()
