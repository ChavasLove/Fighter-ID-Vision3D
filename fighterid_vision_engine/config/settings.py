"""
FighterID Vision Engine — configuración central
Lee variables desde .env (o del entorno del sistema).

Crea un archivo .env en la raíz del proyecto con el contenido de .env.example.
Las credenciales NO están hardcodeadas aquí — deben definirse en .env.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Sin python-dotenv, usa solo os.environ

# ── Supabase ──────────────────────────────────────────────────────────
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL:
    print("[CONFIG] ⚠  SUPABASE_URL no definida — crea .env desde .env.example")
if not SUPABASE_ANON_KEY:
    print("[CONFIG] ⚠  SUPABASE_ANON_KEY no definida — crea .env desde .env.example")

# ── URL validation helper ──────────────────────────────────────────────
def _require_url(env_key: str, fallback: str) -> str:
    """
    Lee env_key del entorno. Si el valor no empieza con 'http' (p.ej. se puso
    una API key por error), imprime un aviso claro y usa el fallback calculado.
    Esto evita el error 'Invalid URL sb_publishable_...' al arrancar el motor.
    """
    val = os.getenv(env_key, "").strip()
    if val.startswith("http"):
        return val
    if val:
        print(
            f"[CONFIG] ⚠  {env_key}={val!r} no es una URL válida "
            f"(¿pusiste la API key en lugar de la URL?).\n"
            f"         Usando valor por defecto: {fallback}"
        )
    return fallback


# ── Edge Functions ─────────────────────────────────────────────────────
FIGHTERID_EDGE_URL = _require_url(
    "FIGHTERID_EDGE_URL",
    f"{SUPABASE_URL}/functions/v1",
)
FIGHTERID_API_URL  = _require_url(
    "FIGHTERID_API_URL",
    f"{SUPABASE_URL}/functions/v1/ai-strike-ingest",
)
FIGHTERID_API_KEY  = os.getenv("FIGHTERID_API_KEY", SUPABASE_ANON_KEY)

# ── Interruptor general de API ─────────────────────────────────────────
API_ENABLED = os.getenv("API_ENABLED", "true").strip().lower() == "true"

# ── Identidad del motor ────────────────────────────────────────────────
DEVICE_ID = os.getenv("DEVICE_ID", "vision_engine_01")

# ── Cámara — resolución 720p para USB (más estable que 1080p) ─────────
CAM_W = int(os.getenv("CAM_W", "1280"))
CAM_H = int(os.getenv("CAM_H", "720"))

# ── Umbrales de detección de golpes (ajustar según setup físico) ───────
STRIKE_SPEED_MS = float(os.getenv("STRIKE_SPEED_MS", "3.5"))   # m/s velocidad mínima de muñeca
STRIKE_DIST_M   = float(os.getenv("STRIKE_DIST_M",   "0.15"))  # m distancia máxima al oponente
STRIKE_COOL_S   = float(os.getenv("STRIKE_COOL_S",   "0.50"))  # s cooldown entre golpes

# Píxeles por metro — para 720p a ~2m de distancia. Calibrar según setup.
PIX_PER_M = float(os.getenv("PIX_PER_M", "200.0"))

# Umbral de confianza para detección de pose (0.0–1.0)
# 0.35 por defecto: más permisivo que el 0.45 original.
# Subir a 0.50 si hay demasiados falsos positivos en el ring.
POSE_CONF_THR = float(os.getenv("POSE_CONF_THR", "0.25"))

# ── Intervalo de push de métricas al dashboard ─────────────────────────
STATS_INTERVAL_S = float(os.getenv("STATS_INTERVAL_S", "1.5"))  # segundos entre cada POST /stats

# ── COCO keypoint indices ──────────────────────────────────────────────
KP_NOSE      = 0
KP_L_SHOULDER= 5
KP_R_SHOULDER= 6
KP_L_ELBOW   = 7
KP_R_ELBOW   = 8
KP_L_WRIST   = 9
KP_R_WRIST   = 10
KP_L_HIP     = 11
KP_R_HIP     = 12

# ── Análisis temporal de golpes ────────────────────────────────────────
TEMPORAL_WINDOW_FRAMES  = int(os.getenv("TEMPORAL_WINDOW_FRAMES",  "15"))
STRIKE_ACCEL_THRESHOLD  = float(os.getenv("STRIKE_ACCEL_THRESHOLD", "20.0"))  # m/s²
STRIKE_DECEL_REQUIRED   = os.getenv("STRIKE_DECEL_REQUIRED", "true").lower() == "true"
MULTICAM_CONFIRM_MS     = float(os.getenv("MULTICAM_CONFIRM_MS",    "80.0"))   # ms ventana cross-cámara

# ── Clasificación de golpes ────────────────────────────────────────────
JAB_MAX_EXTENSION_M     = float(os.getenv("JAB_MAX_EXTENSION_M",    "0.25"))   # m extensión máx jab
CROSS_MIN_EXTENSION_M   = float(os.getenv("CROSS_MIN_EXTENSION_M",  "0.35"))   # m extensión mín cross
HOOK_LATERAL_RATIO      = float(os.getenv("HOOK_LATERAL_RATIO",     "0.6"))    # ratio lateral para hook
UPPERCUT_VERTICAL_RATIO = float(os.getenv("UPPERCUT_VERTICAL_RATIO","0.5"))    # ratio vertical para uppercut

# ── V5 PRO Visual Engine ───────────────────────────────────────────────
REPLAY_SPEED_THRESHOLD = float(os.getenv("REPLAY_SPEED_THRESHOLD", "5.5"))  # m/s para trigger replay
REPLAY_BUFFER_FRAMES   = int(os.getenv("REPLAY_BUFFER_FRAMES",   "120"))    # ~4s @ 30fps
HIT_EFFECT_FRAMES      = int(os.getenv("HIT_EFFECT_FRAMES",       "18"))    # duración animación HIT
HEATMAP_BLUR_RADIUS    = int(os.getenv("HEATMAP_BLUR_RADIUS",     "30"))    # radio blur gaussiano (px)

# ── Versiones del motor (control de versiones en cada evento) ──────────
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1.0.0")   # versión del modelo de detección
RULES_VERSION = os.getenv("RULES_VERSION", "v1.0.0")   # versión del motor de reglas de boxeo

# ── Feature Flags — activar/desactivar subsistemas sin redeploy ────────
FF_NEW_SCORING_ENGINE  = os.getenv("FF_NEW_SCORING_ENGINE",  "true").strip().lower() == "true"
FF_NEW_HIT_FILTERS     = os.getenv("FF_NEW_HIT_FILTERS",     "true").strip().lower() == "true"
FF_NEW_DETECTION_MODEL = os.getenv("FF_NEW_DETECTION_MODEL", "false").strip().lower() == "true"
FF_EMIT_SCORING_EVENTS = os.getenv("FF_EMIT_SCORING_EVENTS", "true").strip().lower() == "true"

# ── Buffer de reintentos (eventos que no pudieron enviarse a Supabase) ─
RETRY_BUFFER_PATH  = os.getenv("RETRY_BUFFER_PATH",  "buffer/pending_events.jsonl")
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "5"))
