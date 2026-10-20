"""
fase3_optuna.py — Optimización bayesiana multi-objetivo por horizonte
(sección 7, Fase 3).

JERARQUÍA REEMPLAZADA el 2026-10-19 (ver INSTRUCCIONES.md sección 3):
  P0 = validez (restricción, vía trial.set_constraint).
  P1 = minimizar desv_media_max (|media(v_cap) - 150V|, peor de los 6).
  P2 = minimizar osc_max (oscilación pico-pico v_cap) — objetivo principal.
Optuna corre en modo MULTI-OBJETIVO (directions=["minimize", "minimize"]
sobre [desv_media_max, osc_max]) y devuelve un frente de Pareto
(study.best_trials). La Fase 4 aplica el orden lexicográfico estricto
P1>P2>P3 (con P3 = desempate por I.DC, que Optuna no optimiza activamente)
sobre los resultados en simulaciones.csv para la selección final.

Un estudio Optuna por horizonte, en orden creciente, con almacenamiento SQLite
local (NO se sincroniza entre máquinas — cada máquina mantiene su propio
sampler; ver INSTRUCCIONES.md "Ejecución multi-máquina"). Los RESULTADOS de
simulación sí se comparten vía simulaciones.csv (git_sync.py), evitando
duplicar simulaciones exactas entre máquinas.

Uso:
    python fase3_optuna.py                  # todos los horizontes, solo esta máquina
    python fase3_optuna.py --git             # coordina con otras máquinas vía GitHub
    python fase3_optuna.py --horizonte 3     # solo ese horizonte
    python fase3_optuna.py --horizonte 3 --git
"""

import argparse
import json

import optuna
from optuna.samplers import TPESampler

import config
from simulador import simular_punto

VCAP_NOMBRES = ["ap", "bp", "cp", "an", "bn", "cn"]


def cargar_rangos_log10() -> dict:
    """Rango [exp_min, exp_max] por peso optimizable, en décadas respecto a
    PESOS_BASE. Usa resultados/fase2_conclusiones.json si existe (y el peso no
    quedó fijado en FIJAR_EN_BASE); si no, RANGO_LOG10 genérico de config.

    Respeta config.PESOS_IGUALES: solo el primer peso de cada par (q11, q44)
    se trata como variable independiente; el segundo (q22, q55) se deriva
    igual al primero al aplicar el punto."""
    rango_generico = list(config.RANGO_LOG10)
    conclusiones_path = config.RESULTADOS_DIR / "fase2_conclusiones.json"

    pesos_dependientes = {b for _, b in config.PESOS_IGUALES}
    pesos_a_optimizar = [p for p in config.NOMBRES_PESOS if p not in pesos_dependientes]
    rangos = {p: rango_generico for p in pesos_a_optimizar}

    if conclusiones_path.exists():
        with open(conclusiones_path, "r", encoding="utf-8") as f:
            conclusiones = json.load(f)
        for peso, c in conclusiones.items():
            if peso not in rangos:
                continue
            if c.get("accion") == "FIJAR_EN_BASE":
                pesos_a_optimizar.remove(peso)
                del rangos[peso]
            elif c.get("accion") == "OPTIMIZAR" and c.get("rango_valido_log10"):
                rangos[peso] = c["rango_valido_log10"]

    return pesos_a_optimizar, rangos


def _expandir_pesos_iguales(pesos: dict) -> dict:
    """Copia el valor del peso independiente al dependiente (q11->q22, q44->q55)."""
    pesos = dict(pesos)
    for independiente, dependiente in config.PESOS_IGUALES:
        pesos[dependiente] = pesos[independiente]
    return pesos


def construir_objetivo(horizonte: int, pesos_a_optimizar: list, rangos: dict, usar_git: bool):
    def objetivo(trial: optuna.Trial):
        pesos = dict(config.PESOS_BASE)
        for peso in pesos_a_optimizar:
            exp_min, exp_max = rangos[peso]
            exp = trial.suggest_float(peso, exp_min, exp_max)
            pesos[peso] = config.PESOS_BASE[peso] * (10.0 ** exp)
        pesos = _expandir_pesos_iguales(pesos)

        fila = simular_punto(horizonte=horizonte, pesos=pesos, fase="fase3", usar_git=usar_git)

        if fila is None:
            # Punto tomado por otra máquina.
            trial.set_constraint("c0_valida", 1e6)
            raise optuna.TrialPruned()

        estado = fila["estado"]
        if estado in ("FALLIDA", "TIMEOUT", "INVALIDA"):
            trial.set_constraint("c0_valida", 1e6)
            trial.set_user_attr("sim_id", fila["id"])
            trial.set_user_attr("estado", estado)
            return 1e6, 1e6

        valida_P0 = fila["valida_P0"] in ("True", True)
        trial.set_constraint("c0_valida", 0.0 if valida_P0 else 1.0)
        trial.set_user_attr("sim_id", fila["id"])
        trial.set_user_attr("estado", estado)

        desv_media_max = float(fila["desv_media_max"])
        osc_max = float(fila["osc_max"])
        return desv_media_max, osc_max

    return objetivo


def _es_factible(t: optuna.trial.FrozenTrial) -> bool:
    c = t.system_attrs.get("constraints")
    return c is not None and all(x <= 0 for x in c)


def contar_factibles_diversos(study: optuna.Study) -> int:
    """Cuenta candidatos factibles (P0) en el frente de Pareto cuya distancia
    máxima en log10 entre ellos es >= DIST_MIN_LOG10 en al menos un peso
    (criterio de diversidad de la Fase 4), de forma voraz."""
    factibles = [t for t in study.best_trials if _es_factible(t)]
    if not factibles:
        return 0

    factibles.sort(key=lambda t: t.values[1])  # ordenar por P2 (osc_max)
    seleccionados = [factibles[0]]
    for t in factibles[1:]:
        diverso = all(
            max(abs(t.params[p] - s.params[p]) for p in t.params) >= config.DIST_MIN_LOG10
            for s in seleccionados
        )
        if diverso:
            seleccionados.append(t)

    return len(seleccionados)


def hacer_callback_parada(horizonte: int):
    mejor_historial = []

    def callback(study: optuna.Study, trial: optuna.trial.FrozenTrial):
        n = len(study.trials)
        if n < config.PRUEBAS_MIN_POR_HORIZONTE:
            return

        factibles = [t for t in study.trials if _es_factible(t)]
        mejor_osc = min((t.values[1] for t in factibles), default=None)
        mejor_historial.append(mejor_osc)

        if n >= config.PRUEBAS_MAX_POR_HORIZONTE:
            study.stop()
            return

        if len(mejor_historial) > config.PACIENCIA:
            ventana = mejor_historial[-config.PACIENCIA:]
            validos = [v for v in ventana if v is not None]
            if len(validos) >= 2:
                mejora_pct = abs(validos[-1] - validos[0]) / validos[0] * 100 if validos[0] else 0
                n_diversos = contar_factibles_diversos(study)
                if mejora_pct <= 1.0 and n_diversos >= 9:
                    study.stop()

    return callback


def ampliar_rango_si_border(study: optuna.Study, pesos_a_optimizar: list, rangos: dict) -> bool:
    """Si el mejor punto (por P2) queda a <0.25 décadas del borde en algún
    peso, amplía ese rango 1 década (hasta el límite absoluto)."""
    factibles = [t for t in study.best_trials if _es_factible(t)]
    if not factibles:
        return False

    mejor = min(factibles, key=lambda t: t.values[1])
    limite_abs_min, limite_abs_max = config.RANGO_LOG10_LIMITE
    algo_amplio = False

    for peso in pesos_a_optimizar:
        exp_min, exp_max = rangos[peso]
        valor = mejor.params[peso]
        if valor - exp_min < 0.25 and exp_min > limite_abs_min:
            rangos[peso] = [max(exp_min - 1, limite_abs_min), exp_max]
            algo_amplio = True
        if exp_max - valor < 0.25 and exp_max < limite_abs_max:
            rangos[peso] = [rangos[peso][0], min(exp_max + 1, limite_abs_max)]
            algo_amplio = True

    return algo_amplio


def optimizar_horizonte(horizonte: int, indice_horizonte: int, usar_git: bool):
    print(f"\n{'='*60}\n  Fase 3: Optuna (multi-objetivo P1,P2) para horizonte N={horizonte}\n{'='*60}")

    pesos_a_optimizar, rangos = cargar_rangos_log10()
    print(f"  Pesos a optimizar: {pesos_a_optimizar} "
          f"(q22=q11 y q55=q44 se derivan automáticamente)")
    print(f"  Rangos (log10 décadas respecto a base): {rangos}")

    sampler = TPESampler(
        multivariate=True,
        seed=config.SEMILLA + indice_horizonte,
        n_startup_trials=12,
    )

    study = optuna.create_study(
        storage=f"sqlite:///{config.OPTUNA_DB}",
        study_name=f"horizonte_{horizonte}",
        load_if_exists=True,
        sampler=sampler,
        directions=["minimize", "minimize"],  # [desv_media_max (P1), osc_max (P2)]
    )

    # Punto inicial: caso base (log10=0 en todos los pesos optimizables).
    punto_base = {p: 0.0 for p in pesos_a_optimizar}
    study.enqueue_trial(punto_base, skip_if_exists=True)

    objetivo = construir_objetivo(horizonte, pesos_a_optimizar, rangos, usar_git)
    callback = hacer_callback_parada(horizonte)

    n_restantes = max(0, config.PRUEBAS_MAX_POR_HORIZONTE - len(study.trials))
    if n_restantes > 0:
        study.optimize(objetivo, n_trials=n_restantes, callbacks=[callback],
                        catch=(Exception,))

    # Expansión de rango si el mejor punto queda cerca del borde.
    while ampliar_rango_si_border(study, pesos_a_optimizar, rangos):
        print("  Ampliando rango por cercanía al borde, continuando optimización...")
        objetivo = construir_objetivo(horizonte, pesos_a_optimizar, rangos, usar_git)
        study.optimize(objetivo, n_trials=20, callbacks=[callback], catch=(Exception,))

    n_diversos = contar_factibles_diversos(study)
    if n_diversos < 9:
        print(f"  Solo {n_diversos} candidatos factibles diversos; corriendo "
              f"{config.PRUEBAS_EXTRA_EXPLORATORIAS} pruebas exploratorias extra...")
        sampler_explorador = optuna.samplers.QMCSampler(seed=config.SEMILLA + indice_horizonte + 1000)
        study.sampler = sampler_explorador
        study.optimize(objetivo, n_trials=config.PRUEBAS_EXTRA_EXPLORATORIAS, catch=(Exception,))

    n_diversos_final = contar_factibles_diversos(study)
    factibles = [t for t in study.best_trials if _es_factible(t)]
    mejor_osc = min((t.values[1] for t in factibles), default=None)
    mejor_desv_media = None
    if factibles:
        mejor_trial = min(factibles, key=lambda t: t.values[1])
        mejor_desv_media = mejor_trial.values[0]

    msg = (f"Horizonte {horizonte}: {len(study.trials)} pruebas, "
           f"{len(factibles)} factibles (Pareto), {n_diversos_final} diversos, "
           f"mejor_osc={mejor_osc}, mejor_desv_media={mejor_desv_media}")
    print(f"  {msg}")

    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.PROGRESO_LOG, "a", encoding="utf-8") as f:
        import datetime
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")

    return study


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--git", action="store_true")
    parser.add_argument("--horizonte", type=int, default=None)
    args = parser.parse_args()

    horizontes = [args.horizonte] if args.horizonte is not None else config.HORIZONTES

    print(f"Máquina: {config.MAQUINA_ID}  |  Git: {args.git}  |  Horizontes: {horizontes}")

    if len(config.HORIZONTES) * config.PRUEBAS_MAX_POR_HORIZONTE > config.LIMITE_TOTAL_SIMULACIONES:
        print(f"ADVERTENCIA: el total potencial de simulaciones "
              f"({len(config.HORIZONTES)} x {config.PRUEBAS_MAX_POR_HORIZONTE} = "
              f"{len(config.HORIZONTES) * config.PRUEBAS_MAX_POR_HORIZONTE}) "
              f"podría superar LIMITE_TOTAL_SIMULACIONES={config.LIMITE_TOTAL_SIMULACIONES}. "
              f"Según la sección 6 de INSTRUCCIONES.md, esto requiere confirmación del usuario "
              f"ANTES de proceder. Deteniendo.")
        return

    for h in config.HORIZONTES:
        if h not in horizontes:
            continue
        idx = config.HORIZONTES.index(h)
        optimizar_horizonte(h, idx, args.git)

    print("\nFase 3 completa.")


if __name__ == "__main__":
    main()
