"""
FighterID Vision Engine — configuración central
Lee variables desde .env (o del entorno del sistema).

Crea un archivo .env en la raíz del proyecto con el contenido de .env.example.
Si no existe .env, usa los valores por defecto hardcodeados aquí.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Sin python-dotenv, usa solo os.environ

# ── Supabase ──────────────────────────────────────────────────────────
SUPABASE_URL      = os.getenv(
    "SUPABASE_URL",
    "https://eeshomcqztvjkvycdfwi.supabase.co",
)
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlc2hvbWNxenR2amt2eWNkZndpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNDUyMDAsImV4cCI6MjA3MTgyMTIwMH0"
        ".JbOPpqzJvzojVRP3hV4QuDeetzRVpRxoaZeBAXrCb2c"
    ),
)

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
FIGHTERID_API_KEY  = os.getenv(
    "FIGHTERID_API_KEY",
    SUPABASE_ANON_KEY,
)

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
KP_NOSE    = 0
KP_L_WRIST = 9
KP_R_WRIST = 10
