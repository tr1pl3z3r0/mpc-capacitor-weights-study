"""
fase1_caso_base.py — Simula PESOS_BASE en cada uno de los HORIZONTES.
Este caso es la Prueba 1 de cada bloque en el Excel final (sección 7, Fase 1).

Uso:
    python fase1_caso_base.py
"""

import config
from simulador import simular_punto


def main():
    print("=" * 60)
    print("  Fase 1: caso base en cada horizonte")
    print("=" * 60)

    for h in config.HORIZONTES:
        print(f"\n[Horizonte N={h}] simulando caso base...")
        fila = simular_punto(horizonte=h, pesos=config.PESOS_BASE, fase="fase1")
        estado = fila["estado"]
        osc = fila.get("osc_max", "")
        rms = fila.get("rms_icirc_peor", "")
        print(f"  id={fila['id']}  estado={estado}  osc_max={osc}  rms_icirc_peor={rms}  "
              f"duracion={fila['duracion_s']}s")

    print("\nFase 1 completa. Ver resultados/simulaciones.csv (fase=fase1).")


if __name__ == "__main__":
    main()
