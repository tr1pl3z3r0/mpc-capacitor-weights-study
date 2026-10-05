# INSTRUCCIONES PARA CLAUDE CODE: ajuste de pesos del MPC de capacitores (convertidor multimodular, modelo promedio, PLECS)

Lee todo este documento antes de empezar. Guárdalo como INSTRUCCIONES.md en la carpeta del estudio y vuelve a consultarlo cuando tengas dudas. Crea una lista de tareas con las fases de la sección 7.

## 0. Objetivo
Automatizar, ejecutar y documentar un estudio de simulaciones en PLECS. Para cada uno de los 5 horizontes del MPC (N = 1, 2, 3, 4, 5 — confirmado con el usuario; más allá de N=5 es redundante), encuentra 10 conjuntos distintos de pesos del control de capacitores (q11, q22, q33, q44, q55, r11, r22). Esos conjuntos deben cumplir una oscilación de capacitores menor a 10 V y minimizar las corrientes circulantes. Escribe los resultados en una COPIA de la plantilla "Pruebas_por_peso_MPC._Modelo_promedio.xlsx".

NOTA: la plantilla Excel y el texto original de estas instrucciones mencionan "10 horizontes"; se confirmó con el usuario (2026-09-30) que el estudio real cubre solo 5 horizontes (N=1..5). Donde el documento diga "10 horizontes" o "10 bloques", debe leerse como "5 horizontes" / "5 bloques" — se usarán solo los primeros 5 bloques de la hoja Excel (filas 3 a 77).

Ya existe un script de Python que automatiza PLECS y la toma de datos. REUTILÍZALO; no lo reescribas desde cero.

Los campos marcados [COMPLETAR] pueden venir vacíos. En ese caso, averígualos leyendo el script y el modelo, y confírmalos conmigo en el punto de control de la Fase 0. Nunca supongas un valor [COMPLETAR] sin confirmarlo.

## 1. Contexto fijo del sistema (NO modificar nada de esto)
- Convertidor multimodular, con modelo promedio en los clústers (no conmutado).
- Modo de operación: entrega de potencia al puerto AC, con corrientes de amplitud cercana a 16 A.
- Puerto AC: fuente de 20 V de amplitud y 4 Hz. Puerto DC: fuente de 450 V.
- Capacitores en los clústers: voltaje inicial de 148 V y referencia de 150 V.
- v0: señal signo (cuadrada) de 50 Hz.
- Pesos FIJOS del control de corrientes: Q_Val = 1, R_Val = 1e-3.
- Variables de decisión: SOLO los pesos del control de capacitores, Q = diag(q11..q55) y R = diag(r11, r22), y el horizonte.

## 2. Configuración
Crea config.py con estos valores. Todo el código debe leerlos de ahí.
- RUTA_MODELO_PLECS = [COMPLETAR]
- SCRIPT_EXISTENTE = [COMPLETAR]
- PLANTILLA_EXCEL = "Pruebas_por_peso_MPC._Modelo_promedio.xlsx"
- VARIABLE_HORIZONTE = [COMPLETAR: nombre de la variable en PLECS. Si hay horizonte de predicción y de control, o uno por cada controlador, pregúntame cuál o cuáles variar.]
- HORIZONTES = [COMPLETAR: 10 valores en orden creciente]
- HORIZONTE_REFERENCIA = [COMPLETAR; por defecto, la mediana de HORIZONTES]
- NOMBRES_PESOS = [COMPLETAR: nombres de las variables en PLECS para q11, q22, q33, q44, q55, r11, r22]
- PESOS_BASE = [COMPLETAR; si no se indica, usa los valores actuales del modelo; si no existen, todos = 1]
- SENALES = [COMPLETAR: índice o nombre de cada salida]
    - v_cap: TODAS las señales de voltaje de capacitor (se esperan 3; si hay más, inclúyelas todas)
    - i_circ: todas las corrientes circulantes (una o varias)
    - i_ac: corriente(s) del puerto AC
    - i_ac_ref: opcional
- I_AC_REF = [COMPLETAR: aprox. 16 A; léelo del modelo]
- F_AC = 4 Hz; F_V0 = 50 Hz; V_REF = 150 V
- T_VENTANA = 0.5 s (mínimo común múltiplo de 0.25 s y 0.02 s)
- T_SIM = [se determina en la Fase 0 y queda fijo]
- OSC_MAX = 10.0 V
- DEF_OSCILACION = "pico-pico" (máx − mín). La alternativa es "desviacion_max" (máx |v − 150|). [Confírmalo conmigo.]
- TOL_I_AC = 0.10 (±10 % en la amplitud fundamental de i_ac respecto a I_AC_REF)
- TOL_V_MEDIA = 2.0 V (diferencia permitida entre la media de cada capacitor y 150 V)
- RANGO_LOG10 = [-3, +3] décadas alrededor de PESOS_BASE
- PRUEBAS_MIN_POR_HORIZONTE = 40; PRUEBAS_MAX_POR_HORIZONTE = 80; PACIENCIA = 20
- TOL_EMPATE = 0.01 (1 %)
- DIST_MIN_LOG10 = 0.301 (equivale a un factor 2)
- SEMILLA = 42
- TIMEOUT_SIM = 120 s
- INCLUIR_CASO_BASE_COMO_PRUEBA_1 = True

## 3. Jerarquía de prioridades
La comparación es LEXICOGRÁFICA ESTRICTA: nunca sacrifiques un nivel superior para mejorar uno inferior.
Ejemplo: osc = 9.8 V con RMS = 3 A es MEJOR que osc = 10.2 V con RMS = 0.5 A.

P0. VALIDEZ (obligatoria). Si una simulación falla aquí, se registra pero NO puede seleccionarse.
  a) La simulación terminó sin error, sin NaN/Inf y dentro de TIMEOUT_SIM.
  b) Se alcanzó el régimen permanente (criterio en la sección 4).
  c) [MODIFICADO, confirmado con el usuario 2026-09-30] No existe un scope exportable para i_ac (el punto "Iout"/"Is" del nivel superior no es una ventana de scope real; pywinauto no puede exportarlo). En su lugar, la señal del scope "I. DC" del nivel superior debe estabilizarse cerca de 0: |I.DC| < TOL_I_DC (5 mA) en la ventana de evaluación, después de la estabilización. Esto reemplaza la condición original de amplitud de i_ac dentro de ±TOL_I_AC de I_AC_REF.
  d) La media de CADA capacitor está a no más de TOL_V_MEDIA de 150 V.
  e) Se usaron exactamente los parámetros fijos: Q_Val, R_Val, fuentes, condiciones iniciales y solver.

P1. RESTRICCIÓN DURA: oscilación < 10 V en TODOS los capacitores (se evalúa el peor). NUNCA se relaja.

P2. OBJETIVO PRINCIPAL: minimizar el RMS de la corriente circulante en la ventana. Si hay varias corrientes, se usa la peor.

P3. DESEMPATE (solo si P2 difiere menos de TOL_EMPATE):
  1) menor pico absoluto de corriente circulante: max(|máx|, |mín|);
  2) menor RMSE del voltaje de capacitores respecto a 150 V.

P4. PREFERENCIAS (último desempate; también se reportan en el informe):
  1) mayor margen respecto a 10 V (10 − osc);
  2) menor ITAE;
  3) menor tiempo de simulación.

Si dos reglas entran en conflicto, este es el orden: integridad de datos (sección 5) > P0 > P1 > P2 > P3 > P4 > rapidez.

## 4. Definición exacta de las métricas
Impleméntalas en metricas.py y VALÍDALAS con señales sintéticas antes de usarlas:
- Un seno de amplitud A con paso de tiempo NO uniforme debe dar RMS = A/√2 con error < 0.1 %.
- Un pico-pico conocido debe medirse correctamente.
- La amplitud por Fourier de un seno de 4 Hz debe ser correcta.

Definiciones:
- Ventana de evaluación: [T_SIM − 0.5 s, T_SIM].
  Se usan 0.5 s porque contienen un número entero de periodos de 4 Hz (2) y de 50 Hz (25). Un solo periodo de 4 Hz (0.25 s) contiene 12.5 periodos de 50 Hz y sesgaría el RMS. Explica esto en el informe.
  Guarda también, solo como dato informativo, el RMS en el último periodo de 0.25 s (columna rms_icirc_T025).
- PLECS puede usar paso variable y repetir instantes en los eventos. Por eso NO uses np.mean sobre las muestras: integra con trapecios respecto al tiempo (scipy.integrate.trapezoid o np.trapezoid). Recorta la ventana exactamente, interpolando en los bordes. Los instantes repetidos no son un error.
- RMS(x) = sqrt( ∫ x² dt / T_VENTANA ).
- Oscilación del capacitor k = máx(v_k) − mín(v_k) en la ventana. osc = el máximo entre todos los capacitores.
  Registra además: desv_max = máx |v_k − 150| y la media de cada capacitor.
- Corriente circulante: RMS, máximo (con signo) y mínimo (con signo) en la ventana, como pide la plantilla. pico_abs = max(|máx|, |mín|).
  Si hay varias corrientes, calcula cada una y guárdalas todas en el CSV. Para la tabla y la optimización usa la PEOR.
- RMSE_vcap = máximo sobre k de RMS(v_k − 150) en la ventana.
- ITAE = máximo sobre k de ∫ t·|v_k − 150| dt, calculado sobre TODA la simulación (de 0 a T_SIM), no solo la ventana.
- Amplitud de i_ac: componente de 4 Hz por Fourier sobre la ventana, A = (2/T_VENTANA)·|∫ i(t)·e^(−j2π·4·t) dt|.
- Régimen permanente: compara la ventana final con la anterior, [T_SIM − 1.0 s, T_SIM − 0.5 s]. Exige las tres condiciones:
  |Δ media v_k| ≤ 0.2 V, |Δ osc| ≤ 0.2 V y |Δ RMS i_circ| ≤ 2 %.
  Si no se cumplen, el estado es NO_ESTACIONARIO y la simulación falla P0.

## 5. Reglas inquebrantables
1. No modifiques Q_Val = 1 ni R_Val = 1e-3.
2. No modifiques el archivo del modelo PLECS (.plecs). Si hace falta cambiarlo (por ejemplo, para exponer un peso como variable), DETENTE y pregúntame. Si lo apruebo, trabaja sobre una copia.
3. No cambies fuentes, frecuencias, condiciones iniciales, referencias, número de capacitores ni el tipo de modelo.
4. El solver, sus tolerancias, T_SIM y la resolución de salida se fijan en la Fase 0. Deben ser IDÉNTICOS en todas las simulaciones.
5. No relajes la restricción de 10 V ni ninguna tolerancia de P0 sin mi aprobación.
6. NUNCA inventes, estimes, interpoles ni copies resultados. Cada número de la tabla debe salir de una simulación registrada en el CSV con su ID.
7. Redondea cada peso a 3 cifras significativas ANTES de simular. Así, el valor escrito en la tabla es exactamente el que se simuló.
8. Todos los pesos deben ser > 0. Q y R son diagonales, sin términos fuera de la diagonal.
9. No sobrescribas la plantilla original de Excel ni borres datos crudos. Haz una copia de seguridad del script existente antes de modificarlo.
10. Una simulación fallida NUNCA detiene el estudio: se registra con su estado y se continúa.
11. Corre las simulaciones de una en una. Solo puedes paralelizar si el script existente ya lo hace y está probado.
12. No uses study.best_trial de Optuna para elegir resultados. La selección se hace con la regla de la sección 3, sobre el CSV.
13. Las fases largas se ejecutan como proceso en segundo plano (o en un comando por horizonte), y su avance se sigue en progreso.log. El estudio debe poder REANUDARSE si se interrumpe (CSV + optuna.db).

## 6. Cuándo DETENERTE y preguntarme
- Al terminar la Fase 0 (punto de control obligatorio).
- Si no hay conexión con PLECS (por ejemplo, la interfaz XML-RPC no está activa o PLECS no está abierto).
- Si un peso o el horizonte no se pueden cambiar sin modificar el modelo.
- Si al cambiar un peso o el horizonte las salidas NO cambian, porque el parámetro no se está aplicando.
- Si el caso base no cumple P0: i_ac fuera de tolerancia, media lejos de 150 V o sin régimen permanente.
- Si la misma simulación repetida da resultados distintos (diferencia relativa > 1e-6).
- Si TIMEOUT_SIM se dispara 3 veces seguidas o PLECS deja de responder.
- Si el total de simulaciones va a superar 1200.
- Si algo de la sección 1 no coincide con lo que encuentres en el modelo.
NO te detengas por resultados malos ni por horizontes sin conjuntos factibles: regístralos y sigue.

## 7. Procedimiento
Estimación: entre 500 y 1100 simulaciones, típicamente unas 700. A 10–20 s cada una, son aprox. 2–4 h.
Si faltan dependencias, instálalas: optuna, numpy, scipy, pandas, openpyxl, matplotlib.

### Fase 0: reconocimiento y verificación (aprox. 15 simulaciones)
1. Lee el script existente. Entiende cómo se conecta con PLECS, cómo pasa los parámetros (por ejemplo, ModelVars), qué salidas lee y en qué orden, y cómo configura el solver.
2. Localiza las variables de los 7 pesos, del horizonte y de Q_Val/R_Val, y verifica que Q y R se construyen a partir de ellas.
   NO supongas que las variables derivadas se recalculan al cambiar un parámetro. Eso incluye las matrices Q y R y las matrices de predicción del MPC que dependen del horizonte. Verifícalo con el paso 5b.
3. Verifica el mapeo de las salidas con valores conocidos: v_cap(0) ≈ 148 V; la media de v_cap tiende a 150 V; la amplitud de i_ac ≈ 16 A; la tensión DC es de 450 V, si está disponible.
4. Elige T_SIM. Simula el caso base durante un tiempo largo (por ejemplo, 4 s) y toma T_SIM ≥ tiempo de asentamiento + 1.0 s, con margen. Comprueba el criterio de régimen permanente.
5. Pruebas de verificación:
   a) Repetibilidad: corre el caso base dos veces. Los resultados deben ser idénticos.
   b) Aplicación de parámetros: multiplica cada peso por 100, de uno en uno; las métricas DEBEN cambiar. Haz lo mismo con dos horizontes distintos.
   c) Invariancia de escala: multiplica los 7 pesos por 10 a la vez. Si las métricas son idénticas (diferencia relativa < 1e-6), el costo solo depende de las razones entre pesos. En ese caso, fija r11 en su valor base y optimiza los otros 6. Si no son idénticas, optimiza los 7.
   d) Resolución: reduce a la mitad el paso de salida o el paso máximo. Si el RMS, el pico y la osc cambian menos de 1 %, la resolución basta; si no, refínala hasta que se cumpla.
6. PUNTO DE CONTROL. Muéstrame un resumen con:
   - las variables encontradas, el mapeo de señales y los horizontes;
   - T_SIM, la ventana, el solver y la resolución;
   - los resultados de las pruebas a–d y las métricas del caso base;
   - la duración media por simulación y el tiempo total estimado.
   ESPERA mi confirmación. Después de confirmado, ejecuta las Fases 1 a 6 sin pedir más confirmaciones, salvo en los casos de la sección 6.

### Fase 1: caso base (10 simulaciones)
- Simula PESOS_BASE en los 10 horizontes. Este caso será la Prueba 1 de cada bloque.
- Opcional: si el código del MPC permite saber el significado físico de cada estado y de cada entrada, calcula un caso con la regla de Bryson (q_ii = 1/x_i,max², r_jj = 1/u_j,max²). Úsalo como punto inicial en la Fase 3 y documenta los máximos supuestos.

### Fase 2: sensibilidad, un peso a la vez, en HORIZONTE_REFERENCIA (aprox. 37–43 simulaciones)
- Para cada peso optimizable, prueba los valores base × 10^(−3, −2, −1, 0, +1, +2, +3), con los demás pesos en su valor base.
- Grafica osc, RMS y pico de i_circ contra cada peso, en escala logarítmica.
- Si un peso cambia RMS, pico y osc menos de 2 % en todo el rango, fíjalo en su valor base y quítalo de la optimización.
- Si algún valor provoca fallas o invalidez, recorta el rango de ese peso hasta el último valor válido.
- Anota la tendencia de cada peso para el informe (por ejemplo: "subir q11 baja la osc y sube el RMS"). Si una tendencia contradice lo físicamente esperable, señálalo.

### Fase 3: optimización bayesiana por horizonte (Optuna)
- Crea un estudio por horizonte, en orden creciente, con almacenamiento SQLite: storage="sqlite:///resultados/optuna.db", study_name=f"horizonte_{N}", load_if_exists=True.
- Sampler: TPESampler(multivariate=True, seed=SEMILLA + índice del horizonte, n_startup_trials=12, constraints_func=...).
- Variables: el log10 de cada peso optimizable, con distribución uniforme en su rango (el definido en la Fase 2). El peso es 10^x, redondeado a 3 cifras significativas antes de simular.
- Objetivo a minimizar: el RMS de i_circ (la peor señal).
- Restricciones: un valor ≤ 0 significa que se cumple. Guárdalas con trial.set_user_attr("constraints", [c1, c2, c3, c4]):
    c1 = osc − OSC_MAX
    c2 = |A_iac / I_AC_REF − 1| − TOL_I_AC
    c3 = máx_k |media(v_k) − 150| − TOL_V_MEDIA
    c4 = 0 si hay régimen permanente; +1 si no
- Si la simulación falla o se agota el tiempo: objetivo = 1e6, todas las restricciones = +1e6 y estado FALLIDA o TIMEOUT.
- Puntos iniciales (con enqueue_trial): el caso base, el caso Bryson si existe, el mejor punto de la Fase 2 y los 5 mejores conjuntos factibles del horizonte anterior.
- Criterio de parada: haz al menos PRUEBAS_MIN_POR_HORIZONTE pruebas. Para antes de PRUEBAS_MAX_POR_HORIZONTE solo si se cumplen las dos condiciones:
  1) el mejor RMS factible no mejoró más de 1 % en las últimas PACIENCIA pruebas;
  2) ya hay al menos 9 candidatos factibles diversos, según el criterio de la Fase 4.
  Implementa esta parada con un callback que llame a study.stop().
- Si el mejor punto queda a menos de 0.25 décadas del borde del rango en algún peso, amplía ese rango 1 década y continúa. El límite absoluto es de 1e-6 a 1e6 veces el valor base.
- Si al llegar al máximo hay menos de 9 candidatos factibles diversos, corre hasta 20 pruebas extra con muestreo exploratorio (QMCSampler o aleatorio) dentro de los rangos y vuelve a seleccionar.

### Fase 4: selección de los 10 conjuntos por horizonte
- Prueba 1 = caso base, aunque no cumpla; en ese caso se marca.
- Pruebas 2 a 10: toma los resultados del horizonte que cumplen P0 y P1 y ordénalos con la regla de la sección 3. Elige, de forma voraz, los 9 mejores que difieran entre sí, y del caso base, en al menos un peso por un factor ≥ 2. Es decir, la distancia máxima entre sus log10 debe ser ≥ DIST_MIN_LOG10.
- Si no hay 9 conjuntos factibles diversos, completa con los conjuntos válidos más cercanos a 10 V y márcalos "NO CUMPLE". NUNCA relajes la restricción.
- Ordena las columnas de las Pruebas 2 a 10 de mejor a peor.

### Fase 5: Excel, figuras e informe
Excel: trabaja sobre la copia resultados/Pruebas_por_peso_MPC_resultados.xlsx y conserva el formato y la estructura.
- Hoja "Pruebas realizadas": tiene 10 bloques. El bloque k (k = 0…9) empieza en la fila r = 3 + 15·k. Las columnas C a L son las Pruebas 1 a 10.
    - Fila r: título. Añade el valor del horizonte, por ejemplo "Horizonte N = 5 con los pesos del control de las corrientes en Q_Val = 1, R_Val = 1e-3".
    - Filas r+3 a r+9: q11, q22, q33, q44, q55, r11, r22.
    - Filas r+11 a r+14: Osc. Capacitores (V), RMS corriente circ. (A), Max corriente circ. (A), Min corriente circ. (A).
  Localiza las filas también por su etiqueta en la columna B y comprueba que coinciden con este mapa antes de escribir. Algunas celdas contienen espacios sueltos (por ejemplo, C32): sobrescríbelas. Escribe los valores como números, no como texto.
- Formato:
    - pesos en notación científica (0.00E+00) y métricas con 3 decimales;
    - celda de oscilación en VERDE si es < 10 V y en ROJO si no;
    - la mejor prueba factible de cada bloque en negrita.
- Hoja nueva "Métricas adicionales". Por cada prueba de la tabla incluye: ID de la simulación en el CSV, estado, osc de cada capacitor, desv_max, media de cada capacitor, RMSE_vcap, ITAE, pico_abs, amplitud de i_ac y margen respecto a 10 V.
- Hoja nueva "Resumen": el mejor conjunto de cada horizonte con sus métricas, y el número de simulaciones y de conjuntos factibles por horizonte.
- Hoja nueva "Sensibilidad": los resultados de la Fase 2.

Figuras (PNG, en resultados/figuras/):
- La sensibilidad de cada peso (Fase 2).
- Para cada horizonte: dispersión de RMS de i_circ contra osc de todas las pruebas, con una línea en 10 V y los conjuntos seleccionados resaltados.
- El mejor RMS factible, y su osc, contra el horizonte.
- Formas de onda (todos los v_cap e i_circ) del caso base y del mejor conjunto de cada horizonte.

Informe (resultados/informe.md, en español). Debe incluir:
- la configuración usada;
- las definiciones de las métricas y su justificación (incluida la ventana de 0.5 s);
- los resultados de la Fase 0 y de la sensibilidad;
- el mejor conjunto por horizonte y el efecto del horizonte;
- los horizontes sin conjuntos factibles y las anomalías;
- una lista de SUPUESTOS QUE DEBO VALIDAR.

### Fase 6: verificación final
- Vuelve a simular el mejor conjunto de cada horizonte y 5 entradas aleatorias de la tabla. Sus métricas deben coincidir con el CSV, dentro de la tolerancia de repetibilidad medida en la Fase 0.
- Comprueba por código que cada celda del Excel coincide con su fila del CSV.
- Comprueba que todas las celdas de pesos y métricas de los 10 bloques están llenas.
- Si hay discrepancias, REPÓRTALAS; no las corrijas en silencio.

## 8. Registro y archivos
Estructura de carpetas:
  estudio_mpc/
    INSTRUCCIONES.md
    config.py
    plecs_runner.py        (envuelve el script existente)
    metricas.py            (y sus pruebas con señales sintéticas)
    fase0_verificacion.py … fase6_verificacion.py
    resultados/
      simulaciones.csv
      optuna.db
      formas_onda/         (.npz, solo del caso base y de los conjuntos seleccionados)
      figuras/
      Pruebas_por_peso_MPC_resultados.xlsx
      informe.md
      progreso.log

simulaciones.csv lleva una fila por simulación. Escríbela y guárdala (flush) en cuanto termina cada simulación. Columnas:
- id, fecha_hora, fase, horizonte
- q11, q22, q33, q44, q55, r11, r22, Q_Val, R_Val, T_SIM
- estado (OK / FALLIDA / TIMEOUT / NO_ESTACIONARIO / INVALIDA)
- osc de cada capacitor, osc_max, desv_max, media de cada capacitor
- rms_icirc de cada señal y de la peor, rms_icirc_T025, max_icirc, min_icirc, pico_abs_icirc
- rmse_vcap, itae, amp_iac
- valida_P0, cumple_P1, duracion_s, semilla

Antes de simular, comprueba si esa combinación exacta (horizonte + pesos redondeados) ya está en el CSV. Si está, reutiliza el resultado en lugar de repetir la simulación.

## 9. Comunicación
- Escribe todo en español.
- Al terminar cada horizonte, escribe una línea en progreso.log y en la consola con: horizonte, número de pruebas, número de factibles, mejor RMS, su osc y el tiempo transcurrido.
- Al terminar cada fase, da un resumen breve.
- Al final, entrega: la lista de entregables, una tabla resumen por horizonte y los supuestos o pendientes que debo revisar.
- No afirmes nada que no esté respaldado por el CSV.
