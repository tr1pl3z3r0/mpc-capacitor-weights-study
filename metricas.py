"""
metricas.py — Definiciones exactas de métricas (ver INSTRUCCIONES.md sección 4).

Todas las integrales se calculan con trapecios respecto al tiempo (no np.mean
sobre las muestras), porque PLECS usa paso variable y puede repetir instantes.
"""

import numpy as np

import config


def recortar_ventana(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float):
    """Recorta [t_ini, t_fin] interpolando exactamente en los bordes.
    Asume t creciente (no estrictamente, puede repetir instantes en eventos)."""
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    mask = (t >= t_ini) & (t <= t_fin)
    t_win = t[mask]
    x_win = x[mask]

    if t_win.size == 0 or t_win[0] > t_ini:
        x_ini = np.interp(t_ini, t, x)
        t_win = np.concatenate(([t_ini], t_win))
        x_win = np.concatenate(([x_ini], x_win))
    if t_win[-1] < t_fin:
        x_fin = np.interp(t_fin, t, x)
        t_win = np.concatenate((t_win, [t_fin]))
        x_win = np.concatenate((x_win, [x_fin]))

    return t_win, x_win


def rms(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float) -> float:
    """RMS(x) = sqrt( integral(x^2 dt) / (t_fin - t_ini) )."""
    t_win, x_win = recortar_ventana(t, x, t_ini, t_fin)
    duracion = t_fin - t_ini
    energia = np.trapezoid(x_win ** 2, t_win)
    return float(np.sqrt(energia / duracion))


def pico_pico(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float) -> float:
    _, x_win = recortar_ventana(t, x, t_ini, t_fin)
    return float(x_win.max() - x_win.min())


def desviacion_max(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float, ref: float) -> float:
    _, x_win = recortar_ventana(t, x, t_ini, t_fin)
    return float(np.max(np.abs(x_win - ref)))


def media_ventana(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float) -> float:
    t_win, x_win = recortar_ventana(t, x, t_ini, t_fin)
    duracion = t_fin - t_ini
    return float(np.trapezoid(x_win, t_win) / duracion)


def amplitud_fourier(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float, freq: float) -> float:
    """A = (2/T) * |integral( x(t) * exp(-j*2*pi*freq*t) dt )| sobre la ventana."""
    t_win, x_win = recortar_ventana(t, x, t_ini, t_fin)
    duracion = t_fin - t_ini
    kernel = x_win * np.exp(-1j * 2 * np.pi * freq * t_win)
    integral_real = np.trapezoid(kernel.real, t_win)
    integral_imag = np.trapezoid(kernel.imag, t_win)
    integral = complex(integral_real, integral_imag)
    return float((2.0 / duracion) * abs(integral))


def itae(t: np.ndarray, x: np.ndarray, ref: float, t_ini: float = 0.0, t_fin: float = None) -> float:
    """ITAE = integral( t * |x(t) - ref| dt ) sobre TODA la simulación (0 a T_SIM)."""
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    if t_fin is None:
        t_fin = t[-1]
    t_win, x_win = recortar_ventana(t, x, t_ini, t_fin)
    integrando = t_win * np.abs(x_win - ref)
    return float(np.trapezoid(integrando, t_win))


def rmse_respecto_ref(t: np.ndarray, x: np.ndarray, t_ini: float, t_fin: float, ref: float) -> float:
    """RMS de (x - ref) en la ventana."""
    t_win, x_win = recortar_ventana(t, x, t_ini, t_fin)
    duracion = t_fin - t_ini
    energia = np.trapezoid((x_win - ref) ** 2, t_win)
    return float(np.sqrt(energia / duracion))


def regimen_permanente(t: np.ndarray, senales_vcap: list, senal_icirc_peor: np.ndarray,
                        t_sim: float, t_ventana: float = None) -> dict:
    """Compara ventana final [T-Tv, T] contra la anterior [T-2*Tv, T-Tv].
    Devuelve dict con 'estacionario' (bool) y los deltas medidos."""
    if t_ventana is None:
        t_ventana = config.T_VENTANA

    t_fin_a, t_ini_a = t_sim, t_sim - t_ventana
    t_fin_b, t_ini_b = t_sim - t_ventana, t_sim - 2 * t_ventana

    delta_media_max = 0.0
    delta_osc_max = 0.0
    for v in senales_vcap:
        media_a = media_ventana(t, v, t_ini_a, t_fin_a)
        media_b = media_ventana(t, v, t_ini_b, t_fin_b)
        delta_media_max = max(delta_media_max, abs(media_a - media_b))

        osc_a = pico_pico(t, v, t_ini_a, t_fin_a)
        osc_b = pico_pico(t, v, t_ini_b, t_fin_b)
        delta_osc_max = max(delta_osc_max, abs(osc_a - osc_b))

    rms_a = rms(t, senal_icirc_peor, t_ini_a, t_fin_a)
    rms_b = rms(t, senal_icirc_peor, t_ini_b, t_fin_b)
    delta_rms_pct = abs(rms_a - rms_b) / rms_b if rms_b != 0 else float("inf")

    estacionario = (
        delta_media_max <= config.TOL_REGIMEN_MEDIA
        and delta_osc_max <= config.TOL_REGIMEN_OSC
        and delta_rms_pct <= config.TOL_REGIMEN_RMS_PCT
    )

    return {
        "estacionario": estacionario,
        "delta_media_max": delta_media_max,
        "delta_osc_max": delta_osc_max,
        "delta_rms_pct": delta_rms_pct,
    }


# ── Pruebas de validación con señales sintéticas (sección 4) ────────────────

def _test_rms_seno_paso_no_uniforme():
    """Un seno de amplitud A con paso NO uniforme debe dar RMS = A/sqrt(2), error < 0.1%."""
    rng = np.random.default_rng(0)
    A = 3.7
    freq = 7.0
    t_fin = 2.0  # periodos enteros de freq=7Hz -> 14 periodos
    n = 5000
    # paso no uniforme: tiempos aleatorios ordenados + extremos
    t = np.sort(rng.uniform(0, t_fin, n))
    t[0], t[-1] = 0.0, t_fin
    x = A * np.sin(2 * np.pi * freq * t)

    r = rms(t, x, 0.0, t_fin)
    esperado = A / np.sqrt(2)
    error_rel = abs(r - esperado) / esperado
    assert error_rel < 0.001, f"RMS seno: error_rel={error_rel:.5f} (esperado <0.1%)"
    print(f"  OK rms_seno_paso_no_uniforme: rms={r:.6f} esperado={esperado:.6f} error={error_rel*100:.4f}%")


def _test_pico_pico_conocido():
    t = np.linspace(0, 1, 1000)
    x = 5.0 * np.sin(2 * np.pi * 3 * t) + 10.0  # pico-pico = 10, centrado en 10
    pp = pico_pico(t, x, 0.0, 1.0)
    assert abs(pp - 10.0) < 1e-2, f"pico-pico esperado~10, obtenido {pp}"
    print(f"  OK pico_pico_conocido: pp={pp:.4f} (esperado ~10)")


def _test_amplitud_fourier_seno_4hz():
    A = 2.5
    freq = 4.0
    t_fin = 0.5  # 2 periodos de 4Hz
    t = np.linspace(0, t_fin, 20000)
    x = A * np.sin(2 * np.pi * freq * t)
    amp = amplitud_fourier(t, x, 0.0, t_fin, freq)
    error_rel = abs(amp - A) / A
    assert error_rel < 0.01, f"Fourier 4Hz: error_rel={error_rel:.5f}"
    print(f"  OK amplitud_fourier_seno_4hz: amp={amp:.6f} esperado={A} error={error_rel*100:.4f}%")


def run_self_tests():
    print("Ejecutando pruebas de validación de metricas.py...")
    _test_rms_seno_paso_no_uniforme()
    _test_pico_pico_conocido()
    _test_amplitud_fourier_seno_4hz()
    print("Todas las pruebas de metricas.py pasaron.")


if __name__ == "__main__":
    run_self_tests()
