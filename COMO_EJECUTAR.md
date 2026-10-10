# Cómo hacer funcionar el estudio

Guía práctica para preparar una máquina Windows y correr el estudio de pesos
del MPC de capacitores. Para el detalle del método (métricas, criterios,
fases) ver `INSTRUCCIONES.md`.

## 1. Requisitos

- Windows (el código usa `pywin32` y `pywinauto` para manejar la ventana de PLECS).
- PLECS Standalone instalado.
- Python 3.10 o superior (marcar "Add Python to PATH" al instalar).
- Git y una cuenta de GitHub con permiso de escritura en
  `tr1pl3z3r0/mpc-capacitor-weights-study`.

## 2. Instalar Git e iniciar sesión en GitHub

En PowerShell:

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
```

Cerrar y volver a abrir PowerShell, y luego:

```powershell
git config --global user.name "Tu Nombre"
git config --global user.email "tu-correo@ejemplo.com"
gh auth login
```

En `gh auth login` elegir: GitHub.com → HTTPS → Login with a web browser.
Esto guarda las credenciales para que `git_sync.py` pueda hacer push sin pedir
contraseña.

## 3. Clonar el repositorio

```powershell
git clone https://github.com/tr1pl3z3r0/mpc-capacitor-weights-study.git
cd mpc-capacitor-weights-study
```

Si ya estaba clonado, actualizarlo con `git pull`.

## 4. Instalar las librerías de Python

```powershell
pip install numpy scipy pandas openpyxl matplotlib optuna pywinauto pyautogui pywin32
```

Comprobar:

```powershell
python -c "import numpy, scipy, pandas, openpyxl, matplotlib, optuna, pywinauto, pyautogui, win32api; print('OK')"
```

## 5. Preparar PLECS

1. Copiar el modelo a la ruta configurada en `config.py` (`RUTA_MODELO_PLECS`):
   `C:\Users\danie\Downloads\MMC_sinmodulacion - Con MPC - trapezoide y con 2V0.plecs`.
   Si en esta máquina está en otra carpeta, cambiar `RUTA_MODELO_PLECS` en
   `config.py` (sin hacer commit de ese cambio).
2. Activar la interfaz XML-RPC: en PLECS, *File → PLECS Preferences → General*,
   marcar "XML-RPC interface" con el puerto **1080** (`PLECS_URL` en `config.py`).
3. Abrir el modelo en PLECS y dejarlo abierto mientras corre el estudio.
4. Abrir las ventanas de los cuatro scopes que se exportan:
   - `Voltaje Capacitores/Scope1` (el de voltajes sin transformar — NO "Scope"
     a secas, que muestra otra señal)
   - `C. Circul`
   - `I. DC`
   - `Osc. Cap` (verificación adicional de oscilación)

## 6. Durante la ejecución

La exportación de los scopes se hace manejando la interfaz de PLECS
(teclado y ventanas), así que:

- No usar el mouse ni el teclado en esa máquina mientras corre.
- No bloquear la pantalla ni dejar que entre el protector de pantalla o la
  suspensión.
- Para abortar en emergencia, llevar el mouse a una esquina de la pantalla
  (`pyautogui.FAILSAFE`) o presionar Ctrl+C en la terminal.

## 7. Correr las fases

Desde la carpeta del repositorio, en orden:

```powershell
python fase1_caso_base.py --git          # caso base en cada horizonte
python fase2_sensibilidad.py --git       # sensibilidad de cada peso
python fase3_optuna.py --git             # optimización (todos los horizontes)
python fase3_optuna.py --horizonte 3 --git   # o solo un horizonte
python fase4_seleccion.py                # elige los 10 conjuntos por horizonte
python fase5_excel.py                    # llena el Excel de resultados
python fase5_figuras.py                  # genera las figuras
python fase5_informe.py                  # genera resultados/informe.md
python fase6_verificacion.py --git       # verificación final
```

- `--git` coordina con las otras máquinas: antes de simular cada punto
  reserva su fila en `resultados/simulaciones.csv` y hace push a `main`, así
  ninguna máquina repite una simulación ya hecha. Sin `--git` la máquina
  trabaja sola y no sube nada.
- Las fases 1, 2, 3 y 6 simulan. Las fases 4 y 5 solo procesan el CSV.
- Si el proceso se corta, volver a lanzar el mismo comando: retoma desde
  `simulaciones.csv` y `resultados/optuna.db`.
- El avance se ve en `resultados/progreso.log`.

## 8. Varias máquinas en paralelo

- Repetir los pasos 2 a 5 en cada máquina.
- Cada máquina corre sus simulaciones de una en una; varias máquinas pueden
  correr a la vez usando `--git`.
- Solo `resultados/simulaciones.csv` se sube a GitHub. Los datos crudos
  (`resultados/raw/`), las figuras y `optuna.db` quedan en cada máquina.
- Antes de las fases 4 y 5, hacer `git pull` para tener todos los resultados.

## 9. Problemas comunes

| Síntoma | Causa probable |
|---|---|
| `No se puede conectar a PLECS en http://localhost:1080/RPC2` | PLECS cerrado o XML-RPC desactivado (paso 5.2). |
| Falla la exportación de un scope | La ventana del scope no está abierta, o se tocó el mouse o el teclado durante la exportación. |
| `git push` pide contraseña o da 403 | Falta `gh auth login` o la cuenta no tiene permiso de escritura en el repositorio. |
| `ModuleNotFoundError` | Falta instalar alguna librería (paso 4). |
| Los resultados no cambian al variar un peso | Los nombres de bloques o variables del modelo no coinciden con `config.py` (`BLOQUE_CAPACITORES`, `BLOQUE_CORRIENTES`, `SCOPES`). |

## 10. Estado de la configuración

Con el modelo "trapezoide y con 2V0" (corregido el 2026-10-10), el caso base
confirmado (`q11=q22=25.0, q33=1.0, q44=q55=1.0, r11=r22=1e-5`, N=1) converge
correctamente: medias de v_cap ≈150 V, oscilación 0.08 V pico-pico. `T_SIM=10s`
ya está confirmado como definitivo (no placeholder).

`TOL_REPETIBILIDAD` (1 %) sigue siendo provisional — pendiente de medición
empírica real en la Fase 0.

Importante: `q11` debe ser siempre igual a `q22`, y `q44` siempre igual a
`q55` (restricción física confirmada con el usuario). `r11` y `r22` sí pueden
variar independientemente. Esto reduce las variables de decisión efectivas de
7 a 5 — ver `PESOS_IGUALES` en `config.py`. Los scripts de Fase 2/3 deben
respetar esta restricción al explorar el espacio de pesos.
