"""
diagnostico_punto.py — Prueba un único punto de diseño (horizonte + pesos)
contra PLECS con mucho detalle de debug, sin pasar por Optuna ni escribir en
simulaciones.csv. Útil para diagnosticar manualmente si un punto converge,
antes de lanzar una búsqueda completa.

Uso:
    python diagnostico_punto.py "nombre" '{"q11": 25.0, "q22": 25.0, "q33": 1.0, "q44": 1.0, "q55": 1.0, "r11": 1e-5, "r22": 1e-5}' 1
"""
import sys
import time
sys.path.insert(0, '.')

import config
import plecs_runner as pr

pr.MODEL_NAME = config.MODEL_NAME
pr.SCOPES = config.SCOPES


def probar_punto(nombre, pesos, horizonte=1):
    print(f"\n--- {nombre} (N={horizonte}): {pesos} ---", flush=True)
    try:
        print("  [debug] verificar_scopes_abiertos...", flush=True)
        pr.verificar_scopes_abiertos()
        print("  [debug] aplicar_punto...", flush=True)
        pr.aplicar_punto(horizonte, pesos, config)
        print("  [debug] run_simulation...", flush=True)
        t0 = time.time()
        pr.run_simulation(timeout=config.TIMEOUT_SIM)
        dur = time.time() - t0
        print(f"  [debug] run_simulation OK en {dur:.1f}s", flush=True)
    except Exception as e:
        print(f"  FALLO/TIMEOUT: {e}", flush=True)
        return False

    tmp = config.RESULTADOS_DIR / "raw" / "_busqueda_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    print("  [debug] exportando v_cap...", flush=True)
    try:
        pr.export_scope_csv("v_cap", tmp / "v_cap.csv")
        print("  [debug] v_cap OK, exportando i_dc...", flush=True)
        pr.export_scope_csv("i_dc", tmp / "i_dc.csv")
        print("  [debug] i_dc OK", flush=True)
    except Exception as e:
        print(f"  ERROR exportando: {e}", flush=True)
        return False

    vcap = pr.read_scope_csv(tmp / "v_cap.csv")
    idc = pr.read_scope_csv(tmp / "i_dc.csv")

    t_max_vcap = vcap["time"].max()
    t_max_idc = idc["time"].max()
    duracion_simulada = min(t_max_vcap, t_max_idc)

    if duracion_simulada < config.T_SIM * 0.99:
        print(f"  SIMULACION TRUNCADA en t={duracion_simulada:.4g}s "
              f"(esperado {config.T_SIM}s). duracion_real={dur:.1f}s "
              f"-- esto puede ser divergencia real O un corte del solver; "
              f"revisar valores.", flush=True)

    vcap_cols = [c for c in vcap.columns if c != "time"]
    t_fin = vcap["time"].max()
    ventana = vcap[vcap["time"] >= t_fin - config.T_VENTANA]
    medias = {c: ventana[c].mean() for c in vcap_cols}
    oscs = {c: ventana[c].max() - ventana[c].min() for c in vcap_cols}

    idc_ventana = idc[idc["time"] >= idc["time"].max() - config.T_VENTANA]
    idc_abs_max = idc_ventana["col1"].abs().max()

    print(f"  duracion_real={dur:.1f}s  t_simulado_hasta={t_fin:.3f}s", flush=True)
    print(f"  Medias v_cap: {[round(v,2) for v in medias.values()]}", flush=True)
    print(f"  Oscilaciones (pico-pico): {[round(v,2) for v in oscs.values()]}", flush=True)
    print(f"  I.DC abs max en ventana: {idc_abs_max:.4f} A (tolerancia {config.TOL_I_DC} A)", flush=True)

    # Criterio real de "estable": medias cerca de 150V (tolerancia laxa de
    # exploración, +-10V) Y oscilacion < OSC_MAX Y llegó a T_SIM completo.
    medias_ok = all(abs(v - config.V_REF) <= 10 for v in medias.values())
    osc_ok = all(v < config.OSC_MAX for v in oscs.values())
    duracion_ok = duracion_simulada >= config.T_SIM * 0.99

    print(f"  medias_ok={medias_ok}  osc_ok={osc_ok}  duracion_ok={duracion_ok}", flush=True)

    return medias_ok and osc_ok and duracion_ok


if __name__ == "__main__":
    import json
    nombre = sys.argv[1]
    pesos = json.loads(sys.argv[2])
    horizonte = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    ok = probar_punto(nombre, pesos, horizonte)
    print(f"\nRESULTADO: {'ESTABLE' if ok else 'NO ESTABLE'}", flush=True)
