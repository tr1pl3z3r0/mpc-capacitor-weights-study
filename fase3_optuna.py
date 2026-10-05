"""
fase3_optuna.py — Optimización bayesiana por horizonte (sección 7, Fase 3).

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
import math

import numpy as np
import optuna
from optuna.samplers import TPESampler

import config
from simulador import simular_punto, buscar_existente


def cargar_rangos_log10() -> dict:
    """Rango [exp_min, exp_max] por peso optimizable, en décadas respecto a
    PESOS_BASE. Usa resultados/fase2_conclusiones.json si existe (y el peso no
    quedó fijado en FIJAR_EN_BASE); si no, RANGO_LOG10 genérico de config."""
    rango_generico = list(config.RANGO_LOG10)
    conclusiones_path = config.RESULTADOS_DIR / "fase2_conclusiones.json"

    pesos_a_optimizar = list(config.NOMBRES_PESOS)
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


def _set_constraints(trial: optuna.Trial, constraints: list):
    """Guarda las restricciones de dos formas: vía la API nueva de Optuna
    (trial.set_constraint, consumida automáticamente por el sampler) y como
    user_attr "constraints" (lista ordenada [c1,c2,c3,c4], tal como pide
    INSTRUCCIONES.md sección 7 Fase 3, usada por nuestra propia lógica de
    selección/diversidad)."""
    nombres = ["c1_osc", "c2_idc", "c3_vmedia", "c4_regimen"]
    for nombre, valor in zip(nombres, constraints):
        trial.set_constraint(nombre, valor)
    trial.set_user_attr("constraints", constraints)


def construir_objetivo(horizonte: int, pesos_a_optimizar: list, rangos: dict, usar_git: bool):
    def objetivo(trial: optuna.Trial) -> float:
        pesos = dict(config.PESOS_BASE)
        for peso in pesos_a_optimizar:
            exp_min, exp_max = rangos[peso]
            exp = trial.suggest_float(peso, exp_min, exp_max)
            pesos[peso] = config.PESOS_BASE[peso] * (10.0 ** exp)

        fila = simular_punto(horizonte=horizonte, pesos=pesos, fase="fase3", usar_git=usar_git)

        if fila is None:
            # Punto tomado por otra máquina: no contar este trial como válido.
            _set_constraints(trial, [1e6, 1e6, 1e6, 1e6])
            raise optuna.TrialPruned()

        estado = fila["estado"]
        if estado in ("FALLIDA", "TIMEOUT", "INVALIDA"):
            _set_constraints(trial, [1e6, 1e6, 1e6, 1e6])
            trial.set_user_attr("sim_id", fila["id"])
            trial.set_user_attr("estado", estado)
            return 1e6

        osc_max = float(fila["osc_max"])
        idc_abs_max = float(fila["idc_abs_max"])
        medias = [float(fila[f"media_vcap_{n}"])
                  for n in ["ap", "bp", "cp", "an", "bn", "cn"]]
        rms_icirc_peor = float(fila["rms_icirc_peor"])

        c1 = osc_max - config.OSC_MAX
        c2 = idc_abs_max - config.TOL_I_DC
        c3 = max(abs(m - config.V_REF) for m in medias) - config.TOL_V_MEDIA
        c4 = 0.0 if fila["valida_P0"] in ("True", True) else 1.0

        _set_constraints(trial, [c1, c2, c3, c4])
        trial.set_user_attr("sim_id", fila["id"])
        trial.set_user_attr("estado", estado)

        return rms_icirc_peor

    return objetivo


def contar_factibles_diversos(study: optuna.Study) -> int:
    """Cuenta candidatos factibles (P0+P1) cuya distancia máxima en log10 entre
    ellos es >= DIST_MIN_LOG10 en al menos un peso (criterio de diversidad de
    la Fase 4), de forma voraz."""
    factibles = []
    for t in study.trials:
        if t.state != optuna.trial.TrialState.COMPLETE:
            continue
        c = t.user_attrs.get("constraints")
        if c is None or any(x > 0 for x in c):
            continue
        factibles.append(t)

    if not factibles:
        return 0

    factibles.sort(key=lambda t: t.value)
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

        factibles = [t for t in study.trials
                     if t.state == optuna.trial.TrialState.COMPLETE
                     and t.user_attrs.get("constraints") is not None
                     and all(x <= 0 for x in t.user_attrs["constraints"])]
        mejor_rms = min((t.value for t in factibles), default=None)
        mejor_historial.append(mejor_rms)

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
    """Si el mejor punto queda a <0.25 décadas del borde en algún peso, amplía
    ese rango 1 década (hasta el límite absoluto). Devuelve True si se amplió
    algo (el llamador debe seguir optimizando)."""
    factibles = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE
                 and t.user_attrs.get("constraints") is not None
                 and all(x <= 0 for x in t.user_attrs["constraints"])]
    if not factibles:
        return False

    mejor = min(factibles, key=lambda t: t.value)
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
    print(f"\n{'='*60}\n  Fase 3: Optuna para horizonte N={horizonte}\n{'='*60}")

    pesos_a_optimizar, rangos = cargar_rangos_log10()
    print(f"  Pesos a optimizar: {pesos_a_optimizar}")
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
        direction="minimize",
    )

    # Puntos iniciales: caso base (log10=0 en todos los pesos optimizables).
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
    factibles = [t for t in study.trials
                 if t.state == optuna.trial.TrialState.COMPLETE
                 and t.user_attrs.get("constraints") is not None
                 and all(x <= 0 for x in t.user_attrs["constraints"])]
    mejor_rms = min((t.value for t in factibles), default=None)
    mejor_osc = None
    if factibles:
        mejor_trial = min(factibles, key=lambda t: t.value)
        mejor_osc = mejor_trial.user_attrs.get("constraints", [None])[0]
        if mejor_osc is not None:
            mejor_osc = mejor_osc + config.OSC_MAX  # deshacer c1 = osc - OSC_MAX

    msg = (f"Horizonte {horizonte}: {len(study.trials)} pruebas, "
           f"{len(factibles)} factibles, {n_diversos_final} diversos, "
           f"mejor_rms={mejor_rms}, mejor_osc={mejor_osc}")
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
