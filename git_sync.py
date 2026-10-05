"""
git_sync.py — Coordinación multi-máquina vía GitHub (simulaciones.csv como
base de datos compartida).

Mecanismo de claim (confirmado con el usuario 2026-10-04):
1. pull antes de cada punto.
2. Verificar que el punto (horizonte + pesos redondeados) no esté ya en el CSV
   con estado OK/NO_ESTACIONARIO/INVALIDA/FALLIDA/TIMEOUT (terminado) ni
   CORRIENDO reciente (de otra máquina, dentro de TIMEOUT_CLAIM_S).
3. Si está libre: agregar una fila con estado=CORRIENDO y maquina_id propio,
   commit y push INMEDIATAMENTE (reservando el punto antes de simular).
4. Si el push falla por conflicto (otra máquina hizo push antes): pull de
   nuevo y reintentar con otro punto (no forzar ni reintentar el mismo).
5. Al terminar de simular, reemplazar esa fila CORRIENDO por el resultado
   final (OK/NO_ESTACIONARIO/INVALIDA/FALLIDA/TIMEOUT), commit y push.

Solo simulaciones.csv se versiona en git (confirmado con el usuario: liviano).
Los CSV crudos de PLECS (v_cap/i_circ/i_dc) y las figuras quedan solo locales
en resultados/raw/ (en .gitignore).
"""

import subprocess
import time
from datetime import datetime, timedelta

import config

GIT_DIR = config.RUTA_ESTUDIO


def _git(*args, check=True):
    result = subprocess.run(
        ["git", *args], cwd=GIT_DIR, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falló:\n{result.stdout}\n{result.stderr}")
    return result


def asegurar_repo_inicializado():
    """Inicializa el repo local y configura el remoto si hace falta. No hace push."""
    git_dir = GIT_DIR / ".git"
    if not git_dir.exists():
        _git("init")
        _git("branch", "-M", "main")

    remotes = _git("remote", check=False).stdout.split()
    if "origin" not in remotes:
        _git("remote", "add", "origin", config.GITHUB_REPO_URL)


def pull():
    """Trae los últimos cambios de origin/main. Falla silenciosamente si el
    remoto todavía no tiene commits (repo recién creado)."""
    _git("fetch", "origin", check=False)
    result = _git("pull", "--rebase", "origin", "main", check=False)
    return result.returncode == 0


def push() -> bool:
    """Intenta push a origin/main. Devuelve True si tuvo éxito, False si hubo
    conflicto (alguien más hizo push antes)."""
    result = _git("push", "origin", "main", check=False)
    return result.returncode == 0


def commit_csv(mensaje: str) -> bool:
    """Agrega y commitea solo simulaciones.csv. Devuelve False si no había
    cambios que commitear."""
    _git("add", str(config.CSV_SIMULACIONES))
    result = _git("commit", "-m", mensaje, check=False)
    return result.returncode == 0


def punto_libre(horizonte: int, pesos_redondeados: dict) -> bool:
    """True si el punto no está ya terminado ni siendo corrido activamente
    (CORRIENDO reciente) por otra máquina."""
    from simulador import _leer_filas_crudas  # import diferido, evita ciclo

    ahora = datetime.now()
    for row in _leer_filas_crudas():
        if int(row["horizonte"]) != horizonte:
            continue
        if not all(abs(float(row[k]) - v) < 1e-12 for k, v in pesos_redondeados.items()):
            continue
        if row["estado"] != "CORRIENDO":
            return False  # ya terminado (en cualquier estado final) -> no libre, reusar
        # CORRIENDO: solo bloquea si es reciente
        try:
            ts = datetime.fromisoformat(row["fecha_hora"])
        except Exception:
            continue
        if ahora - ts < timedelta(seconds=config.TIMEOUT_CLAIM_S):
            return False  # otra máquina lo está corriendo activamente
        # CORRIENDO viejo (máquina caída) -> se considera libre, se puede reclamar
    return True


def reclamar_punto(fila_claim: dict, max_intentos: int = 5) -> bool:
    """Intenta reservar un punto escribiendo una fila CORRIENDO y haciendo
    push inmediato. Devuelve True si el claim fue exitoso (push aceptado)."""
    from simulador import _append_csv  # import diferido, evita ciclo

    for intento in range(max_intentos):
        pull()
        _append_csv(fila_claim)
        commit_csv(f"claim: sim {fila_claim['id']} horizonte={fila_claim['horizonte']} "
                   f"maquina={fila_claim.get('maquina_id', '?')}")
        if push():
            return True
        # Conflicto: descartar el commit local y reintentar con pull fresco.
        _git("reset", "--hard", "HEAD~1", check=False)
        time.sleep(1.0 + intento)
    return False


def sincronizar_resultado_final(mensaje: str, max_intentos: int = 5) -> bool:
    """Push del CSV ya actualizado con el resultado final (reemplazando la fila
    CORRIENDO). Reintenta con pull --rebase si hay conflicto."""
    for intento in range(max_intentos):
        if commit_csv(mensaje):
            if push():
                return True
            pull()  # rebase trae los cambios remotos, reintentar push
            if push():
                return True
        else:
            return True  # nada que commitear (no debería pasar normalmente)
        time.sleep(1.0 + intento)
    return False
