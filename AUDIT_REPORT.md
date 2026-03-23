# AUDITORÍA TÉCNICA — Fighter-ID-Vision3D
**Fecha:** 2026-03-23
**Auditor:** Claude Code — Auditor Técnico Principal (Computer Vision / Sistemas Distribuidos)
**Modo de evaluación:** Producción / Evento en vivo con transmisión
**Fuente de verdad:** Especificación del sistema entregada por el cliente

---

## Especificación evaluada

**Pipeline obligatorio:**
```
Cámara → OBS/ATEM → FFmpeg → Motor de Visión (Python + YOLO) → API Supabase → HUD (React)
```

**Contrato de eventos (inmutable):**
- `START session`
- `EVENT strike`
- `STOP session`

**Identificador maestro:** `fight_id`

**Hardware declarado:** Intel i5-10400, 16 GB RAM, AMD Radeon RX 5700 XT (8 GB), Windows 10 x64

---

## 🟢 CUMPLIMIENTOS — QUÉ SÍ FUNCIONA

1. **`fight_id` nunca se genera localmente** — El motor recibe el UUID de Supabase y no lo inventa. El contrato de identidad maestro se respeta.
2. **Fallback chain de GPU** — DirectML (AMD RX 5700 XT) → CUDA → CPU ONNX → PyTorch. Correcto para el hardware declarado.
3. **Fallback de backend de cámara** — DSHOW → MSMF → ANY. Tolera variaciones de drivers en Windows.
4. **Detección temporal de golpes en 3 capas** — `TemporalStrikeAnalyzer` implementa buffer rolling de velocidades + firma cinemática (pico de velocidad + aceleración + cooldown). Mejora sustancial sobre detección single-frame.
5. **Thread-safety en estado compartido** — `fighters_state.py` usa `threading.Lock()` consistentemente. Sin race conditions detectadas en esa capa.
6. **I/O asíncrono** — Las llamadas a Supabase no bloquean el loop de visión (workers daemon en threads separados).
7. **Heartbeat cada 3 s** — Mantiene `vision_connected=True` en `fight_telemetry_sessions` mientras el motor está activo.
8. **Autodescubrimiento de `fight_id`** — `discover_fight_id()` consulta la sesión activa en Supabase al arrancar, sin necesidad de flag CLI.
9. **Configuración externalizada** — Todos los parámetros críticos (URLs, keys, thresholds) son configurables via `.env`. No están hardcodeados en el módulo principal.
10. **Tracker húngaro (PersistentTracker)** — Mantiene identidades estables cuando los peleadores se cruzan. Tolera hasta `MAX_LOST=10` frames sin detección antes de resetear.
11. **CI/CD bloquea JWTs** — `lint.yml` detecta y falla en commits con tokens hardcodeados. Protección futura activa.
12. **Cola con tamaño máximo** — `deque(maxlen=500)` previene crecimiento ilimitado de memoria en el worker de eventos.

---

## 🔴 FALLOS CRÍTICOS — ROMPEN PRODUCCIÓN

### FC-1: FFmpeg y OBS/ATEM NO existen en el codebase

**Archivos:** Ninguno (solo referencia muerta en `archive/main_gui.py`)

El pipeline especificado es `Cámara → OBS/ATEM → FFmpeg → Motor`. La implementación real usa `cv2.VideoCapture(idx)` directo sobre índice de cámara entero:

```python
# fighterid_vision_engine/camera/capture.py:32-44
for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
    cap = cv2.VideoCapture(self.idx, backend)  # índice entero: 0, 1, 2
```

No hay ninguna referencia a `ffmpeg`, `rtsp://`, `rtmp://`, `VideoCapture("http://")` ni integración con OBS Virtual Camera o ATEM en el código activo. **El pipeline documentado no corresponde al pipeline implementado.** Si el evento usa OBS como mezclador de video, el motor no puede recibir ese feed.

**Impacto en producción:** El motor es incompatible con la arquitectura de transmisión descrita en la especificación.

---

### FC-2: Cámara caída = sistema paralizado de forma permanente y silenciosa

**Archivo:** `fighterid_vision_engine/camera/capture.py:63-74`

```python
def _update(self) -> None:
    while self._running:
        if self._cap is None or not self._cap.isOpened():
            time.sleep(0.05)   # ← busy-wait sin reconexión, para siempre
            continue
        ret, frame = self._cap.read()
        if not ret:
            time.sleep(0.005)  # ← busy-wait sin reconexión, para siempre
```

**Archivo:** `fighterid_vision_engine/pipeline/engine.py:431-434`

```python
frame, ts = self._streams["A"].read()
if frame is None:
    time.sleep(0.01)   # ← el loop principal espera eternamente
    continue
```

Si se desconecta el USB de cámara A en el ring, el hilo de captura entra en un loop de 5 ms indefinido. El loop principal recibe `None` cada 10 ms indefinidamente. **No hay reconexión automática, no hay alerta al operador, no hay log de error diferenciado.** El sistema aparenta estar vivo (el proceso sigue corriendo, el heartbeat sigue enviando `vision_connected=True`) pero no detecta nada.

**Impacto en producción:** En un evento de boxeo, el cable de cámara puede aflojarse. El sistema muere en silencio durante la pelea.

---

### FC-3: JWT tokens de producción hardcodeados en código activo

**Archivos:** `vision_motor_v1.py:62-66`, `supabase_client.py:7-8`

```python
# vision_motor_v1.py (motor standalone de 25 KB — NO es archivo)
_SUPABASE_URL = "https://eeshomcqztvjkvycdfwi.supabase.co"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # JWT completo expuesto
```

`vision_motor_v1.py` no es código legacy — es un motor standalone funcional importado activamente desde `app.py`. Cualquier persona con acceso al repositorio tiene credenciales válidas para leer y escribir en la base de datos de producción.

**Impacto en producción:** Riesgo de acceso no autorizado a datos de todos los eventos almacenados. El CI/CD detectaría esto en commits futuros, pero los tokens ya están en el historial de git.

---

### FC-4: Multi-cámara es cosmético — el motor opera como mono-cámara

**Archivo:** `fighterid_vision_engine/pipeline/engine.py:331-346, 431`

```python
# Inicialización
self.multicam = MultiCamStrikeValidator(min_cameras=1)  # ← min_cameras=1

# Loop principal
frame, ts = self._streams["A"].read()  # ← solo cámara A
persons = self.detector.infer(frame)
# ... cámaras B y C nunca se leen para inferencia
```

Las cámaras B y C se abren (`_start_cameras()`) pero su feed nunca se procesa en el loop de detección. `MultiCamStrikeValidator` con `min_cameras=1` confirma **cualquier golpe detectado por cámara A sin validación cruzada**. El sistema se autodenomina multi-cámara pero opera como mono-cámara en el motor headless (que es el motor de producción según `main.py`).

**Impacto en producción:** La robustez de detección esperada de la arquitectura multi-cámara no existe. Falsos positivos no tienen segundo criterio de validación.

---

### FC-5: Realtime Supabase falla silenciosamente en cada ejecución

**Archivo:** `fighterid_supabase_bridge.py:623-655`

```python
def listen_fight_changes(self):
    def _run():
        try:
            channel = db.channel("fight_sync")
            channel.on("broadcast", {"event": "fight_active"}, handle)
            channel.subscribe()
        except Exception as e:
            msg = str(e)
            if any(k in msg.lower() for k in ("sync client", "async client", "realtime", "not available")):
                pass  # supabase-py sync client doesn't support realtime — non-critical
```

`supabase-py` en modo síncrono no soporta canales realtime. Este bloque falla en **cada** ejecución y el error se descarta explícitamente. El comentario dice "non-critical" pero esto rompe el contrato de sincronización: si el operador cambia de pelea desde la web, el motor nunca recibe la notificación. Solo el polling de `_session_sync_loop` (cada 2 s) detecta el cambio — con hasta 2-30 s de lag, y solo si `api.fight_id` es `None`.

**Impacto en producción:** Eventos de la pelea nueva pueden registrarse bajo el `fight_id` de la pelea anterior durante varios segundos.

---

### FC-6: HUD React no existe en el repositorio

**Verificado:** búsqueda exhaustiva de `*.tsx`, `*.jsx`, `package.json` — resultado: 0 archivos de frontend.

El "sistema completo" según la especificación incluye el HUD como componente final del pipeline. Ese componente no tiene código fuente en este repositorio.

**Impacto en producción:** El sistema está incompleto según su propia especificación.

---

## 🟠 FALLAS IMPORTANTES

### FI-7: Confianza calculada de forma inconsistente entre módulos

**Archivo A:** `fighterid_vision_engine/pipeline/temporal_strike.py:282`
```python
conf = min(speed / 8.0, 1.0)
```

**Archivo B:** `fighterid_supabase_bridge.py:673`
```python
confidence = min(max(speed / 25.0, 0.05), 1.0)
```

Dos módulos distintos calculan la confianza con fórmulas distintas (divisor 8 vs 25). Un golpe a 3.5 m/s (el threshold mínimo) tendrá confianza 0.44 en el motor pero 0.14 en el bridge. Ambas fórmulas son arbitrarias — la confianza real debería derivar del score de detección de pose de YOLO, no de la velocidad del golpe.

---

### FI-8: `PIX_PER_M` no validada en arranque — todos los golpes serán "attempted"

**Archivo:** `fighterid_vision_engine/config/settings.py`
```python
PIX_PER_M = float(os.getenv("PIX_PER_M", "200.0"))
STRIKE_DIST_M = float(os.getenv("STRIKE_DIST_M", "0.15"))
```

Con el default de 200 px/m, la distancia máxima para `strike_connected` es 30 píxeles (muñeca a nariz). Sin calibración específica al ring y posición de cámara, esta distancia nunca se cumple y todos los golpes se clasifican como `strike_attempted`. No hay validación ni advertencia al arranque.

---

### FI-9: `start_session()` sin idempotencia — sesiones duplicables

**Archivo:** `fighterid_vision_engine/pipeline/engine.py:409-423`
```python
while self._running:
    if not self.api.fight_id:
        fight_id = discover_fight_id()
        if fight_id:
            self.api.start_session(fight_id)  # sin guard contra doble llamada
    time.sleep(2)
```

Si `start_session()` tarda más de 2 s (timeout de red), el loop puede invocarlo de nuevo con el mismo `fight_id`. No hay guard de idempotencia. Puede generar sesiones duplicadas en `fight_telemetry_sessions`.

---

### FI-10: Deque de eventos descarta golpes silenciosamente bajo presión de red

**Archivo:** `fighterid_supabase_bridge.py:79`
```python
self._queue = deque(maxlen=500)
```

Con `timeout=5 s` por request y un solo hilo worker procesando eventos secuencialmente, el throughput máximo es ~12 eventos/s. En una pelea activa con buena detección, se pueden generar 3-5 eventos/s. Si la red degrada a 1 request cada 10 s, la cola se llena en ~83 s. A partir de ahí, **los golpes más antiguos se descartan sin log, sin alerta y sin persistencia local**.

---

### FI-11: Tracker fallback horizontal silencioso si scipy no está instalado

**Archivo:** `fighterid_vision_engine/detection/tracker.py:85`
```python
if not self._initialized or not self._tracks or not _SCIPY_OK:
    result = _horizontal_assign(persons)  # Izquierda=rojo, derecha=azul
```

Si `scipy` no está instalado (`_SCIPY_OK = False`), el tracker usa asignación horizontal **en cada frame para toda la pelea**, no solo en la inicialización. El tracker húngaro nunca se activa. No hay log de warning. La instalación de scipy no está verificada en el checklist de arranque.

---

### FI-12: Fallback de `discover_fight_id()` hacia Edge Function no implementado

**Archivo:** `fighterid_vision_engine/pipeline/engine.py:67-91`

El docstring de `discover_fight_id()` describe dos intentos:
1. REST directo a `fight_telemetry_sessions`
2. Edge function `/vision/get-active-session` (fallback)

El código retorna `None` después del primer intento fallido. El segundo intento está comentado/omitido. Si la tabla REST falla, no hay fallback.

---

### FI-13: Métricas pseudoestadísticas enviadas al HUD

**Archivo:** `fighterid_vision_engine/pipeline/fighters_state.py`
```python
"aggressiveness": round(f["punch_count"] / 10, 3),       # Golpes÷10 no tiene unidad
"agility":        round(len(f["last_positions"]) / 20, 3), # Acotado a ≤5 siempre (maxlen=100)
"control":        round(f["hits"] / max(punches, 1), 3),   # Idéntico a accuracy
```

Estas métricas no tienen base estadística. `agility` siempre retorna un valor entre 0 y 5 independiente del movimiento real. `control` duplica `accuracy`. Pueden aparecer en pantalla durante transmisión en vivo.

---

## 🟡 OPTIMIZACIONES VIABLES (sin reescribir arquitectura)

1. **Inconsistencia de reloj** — `capture.py` usa `time.perf_counter()` para timestamps de frame; `temporal_strike.py` usa `time.time()`. Cambiar a `time.monotonic()` en ambos garantiza consistencia sin cambios de sistema.

2. **Guard idempotente en `start_session()`** — Añadir `if self.fight_id == fight_id: return` al inicio del método evita el doble inicio sin cambiar la lógica.

3. **Log con timestamp** — Cambiar todos los `print(f"[TAG] ...")` a `print(f"[{datetime.now():%H:%M:%S}][TAG] ...")` permite diagnóstico post-incidente sin infraestructura de logging.

4. **Verificar scipy al arranque** — Añadir un `print("[WARN] scipy no disponible — tracker en modo horizontal")` si `_SCIPY_OK = False` hace el fallo visible antes de la pelea.

5. **Timeout en stats push** — `_stats_push_loop` lanza requests cada 1.5 s sin verificar si el anterior completó. Añadir un flag `_stats_in_flight` y `timeout=2` previene acumulación de threads bloqueados.

---

## 🔵 RIESGOS OPERATIVOS EN EVENTO REAL

| # | Escenario | Probabilidad | Consecuencia |
|---|-----------|-------------|--------------|
| 1 | Cable USB de cámara A se suelta en el ring | **Alta** | Sistema paralizado sin alerta; operador no lo sabe |
| 2 | Setup usa OBS/ATEM como fuente de video | **Alta** (según spec) | Motor no recibe frames; incompatibilidad total |
| 3 | Red Wi-Fi congestionada durante el evento | **Alta** | Cola de 500 eventos desbordada; golpes perdidos sin log |
| 4 | scipy no instalado en PC de producción | **Media** | Tracker en modo horizontal durante toda la pelea |
| 5 | Peleadores entran al ring con rojo a la derecha | **Media** | Identidades invertidas durante los primeros 10 frames |
| 6 | Dos operadores arrancan el motor simultáneamente | **Media** | Sesiones duplicadas en Supabase; datos mezclados |
| 7 | Corte de internet de 60 s | **Media** | ~720 eventos potenciales descartados silenciosamente |
| 8 | Operador cambia de pelea desde la web | **Media** | Motor sigue enviando a la pelea anterior 2-30 s |
| 9 | GPU se congela en inferencia ONNX | **Baja** | Main thread bloqueado indefinidamente; proceso colgado |
| 10 | Repositorio accedido por tercero | **Alta si es público** | JWT expuesto → acceso completo a DB de producción |

---

## ⚫ SCORE TÉCNICO (0–100)

| Dimensión | Puntos | Máx | Justificación |
|-----------|--------|-----|---------------|
| **Arquitectura** | 5 | 25 | Pipeline especificado no implementado. FFmpeg/OBS ausentes. Multi-cámara cosmético en headless. HUD ausente del repo. |
| **Tiempo real** | 12 | 25 | Inferencia GPU funciona y es async. Pero sin control de latencia explícito, sin métricas de lag end-to-end, sin FPS garantizado mínimo. |
| **Robustez** | 8 | 25 | Sin reconexión de cámara. Cola silencia pérdidas. Sin retry en API. Sin persistencia local de eventos. Sin circuit breaker. |
| **Consistencia** | 13 | 25 | `fight_id` correcto como identificador maestro. Heartbeat funciona. Pero confianza inconsistente, realtime roto, sesiones duplicables. |
| **TOTAL** | **38** | **100** | |

---

## 🚦 VEREDICTO FINAL: **NO-GO**

### Justificación técnica

El sistema presenta una base estructural razonable — inferencia GPU funcional, arquitectura async, tracking con algoritmo húngaro, `fight_id` como identificador consistente — pero tiene **seis fallos críticos que individualmente justifican el NO-GO**:

**FC-1 (Pipeline):** El pipeline real es `cv2.VideoCapture` directo. OBS/ATEM/FFmpeg no existen en el código activo. Si el evento usa la arquitectura de transmisión descrita en la especificación, el motor es físicamente incompatible.

**FC-2 (Cámara):** Una desconexión USB durante la pelea mata silenciosamente toda la detección. El heartbeat sigue reportando el motor como activo mientras no detecta nada. Sin alerta, sin recovery.

**FC-3 (Seguridad):** JWT tokens de producción vivos en código fuente activo. Credenciales de toda la base de datos del evento expuestas.

**FC-4 (Multi-cámara):** El sistema opera como mono-cámara en runtime. La validación cruzada de golpes entre cámaras — que es la principal defensa contra falsos positivos — no existe en producción.

**FC-5 (Realtime):** La sincronización automática de `fight_id` via Supabase Realtime falla silenciosamente en cada ejecución. El motor puede enviar eventos a la pelea incorrecta.

**FC-6 (HUD):** El frontend React no está en el repositorio. El sistema está incompleto.

### Condiciones mínimas para GO condicional

1. Documentar explícitamente que el pipeline real es OpenCV directo (o implementar ingesta RTSP/FFmpeg)
2. Implementar reconexión de cámara con backoff y alerta al operador
3. Rotar las credenciales Supabase expuestas y eliminar los tokens del historial git
4. Confirmar que scipy está instalado en el entorno de producción y loguear warning si no
5. Verificar que el HUD existe y está deployado antes del evento

---

*Auditoría generada el 2026-03-23. Basada en análisis estático completo del repositorio.*
*Archivos analizados: 45+ | Líneas de código revisadas: ~15,000*
