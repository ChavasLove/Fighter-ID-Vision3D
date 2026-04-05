"""
FighterID Vision — Supabase Bridge v2.3
Reemplaza la clase FighterIDAPI de main.py.

Edge Functions disponibles:
  vision-start-session
    POST /              → Crea sesión en vision_sync_sessions
    POST /connect       → Motor marca vision_connected: true
    POST /telemetry     → Actualiza heartbeat en fight_telemetry_sessions

  ai-strike-ingest (v2.1)
    POST /start         → Inicia sesión de inferencia
    POST /event         → Inserta golpes en ai_strike_events
    POST /stop          → Detiene sesión con métricas
    POST /end           → Calcula estadísticas finales
    GET  /health        → Health check

Flujo de datos:
  start_session()
    → GET  fight_telemetry_sessions (status=active)
    → GET  fighter_profiles (red + blue)
    → POST vision-start-session/          (crea sync session)
    → POST vision-start-session/connect   (vision_connected=true)
    → POST ai-strike-ingest/start         (inicia inferencia)

  send()  [por cada golpe detectado]
    → INSERT fight_telemetry_events  (directo a DB)
    → fallback: POST ai-strike-ingest/event

  _heartbeat_worker()  [cada 3s mientras hay pelea]
    → DB   UPDATE fight_telemetry_sessions.vision_connected / last_heartbeat
    → fallback: POST vision-start-session/telemetry

  end_fight()
    → POST ai-strike-ingest/stop
    → POST ai-strike-ingest/end
"""

import threading
import time
import uuid as _uuid_mod
from collections import deque

import requests

# Config — lee de .env via fighterid_vision_engine.config.settings
# Esto reemplaza el antiguo "import main as m" que acoplaba el bridge al GUI.
from fighterid_vision_engine.config import settings as _cfg

# ---------------------------------------------------------------------------
# Optional supabase-py client (pip install supabase)
# If not installed the bridge falls back to edge-function HTTP calls.
# ---------------------------------------------------------------------------
try:
    from supabase import create_client as _supa_create
    _SUPABASE_SDK = True
except ImportError:
    _SUPABASE_SDK = False

_PUNCH_TYPE_MAP = {
    "jab":      "jab",
    "cross":    "cross",
    "hook":     "hook",
    "uppercut": "uppercut",
    "overhand": "other",
    "bodyshot": "body_kick",
    "unknown":  "other",
}
_FIGHTER_MAP = {"red": "A", "blue": "B", "test": "A"}

_HEARTBEAT_INTERVAL = 3   # seconds


class FighterIDAPI:

    def __init__(self):
        self._queue         = deque(maxlen=500)
        self._session_queue = deque(maxlen=20)

        # Mutex para estado compartido entre threads worker / session / heartbeat
        self._state_lock = threading.Lock()

        # Session state  (inicializar ANTES de arrancar cualquier hilo para
        # evitar AttributeError en race conditions con listen_fight_changes)
        self._db            = None          # supabase client (lazy)
        self._session_id    = None          # fight_telemetry_sessions.id (uuid)
        self._session_token = None          # fight_telemetry_sessions.session_token
        self._fight_id      = None          # fight_telemetry_sessions.fight_id
        self._round_num     = 1

        # Fighter state (loaded from fighter_profiles)
        self._fighter_red_id      = None
        self._fighter_blue_id     = None
        self._fighter_red_name    = "Rojo"
        self._fighter_blue_name   = "Azul"
        # Extended profiles — populated by fetch_fight_context() or _load_fighters()
        self._fighter_red_profile  = {}   # {nickname, record, weight_class, gym}
        self._fighter_blue_profile = {}

        self._thread    = threading.Thread(target=self._worker,
                          daemon=True, name="FighterIDAPI")
        self._session   = threading.Thread(target=self._session_worker,
                          daemon=True, name="FighterIDSession")
        self._heartbeat = threading.Thread(target=self._heartbeat_worker,
                          daemon=True, name="FighterIDHeartbeat")
        self._thread.start()
        self._session.start()
        self._heartbeat.start()

        self.sent_ok    = 0
        self.sent_err   = 0

        # Realtime subscription — re-sync if web changes the active fight_id
        self.listen_fight_changes()

    # ------------------------------------------------------------------
    # Name resolution helper
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_name(row: dict, fallback: str = "Sin nombre") -> str:
        """
        Resolves a fighter display name from a fighter_profiles row.
        Tries: full_name → name → fallback.
        Handles both DB column conventions (full_name vs name).
        """
        val = row.get("full_name") or row.get("name") or fallback
        return val.strip() if isinstance(val, str) and val.strip() else fallback

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def fight_id(self): return self._fight_id or ""
    @fight_id.setter
    def fight_id(self, v): self._fight_id = v

    @property
    def round_number(self): return self._round_num
    @round_number.setter
    def round_number(self, v): self._round_num = v

    # ------------------------------------------------------------------
    # Supabase client (lazy init)
    # ------------------------------------------------------------------

    def _get_db(self):
        """Return supabase-py client, initialising it on first call."""
        if self._db is not None:
            return self._db
        if not _SUPABASE_SDK:
            return None
        try:
            if not _cfg.SUPABASE_URL or not _cfg.SUPABASE_ANON_KEY:
                return None
            self._db = _supa_create(_cfg.SUPABASE_URL, _cfg.SUPABASE_ANON_KEY)
        except Exception as e:
            print(f"[FighterIDAPI] supabase client init error: {e}")
        return self._db

    def _reset_db(self):
        """Descarta el cliente Supabase — fuerza reconexión en el próximo _get_db()."""
        self._db = None

    @staticmethod
    def _is_disconnect(exc) -> bool:
        s = str(exc).lower()
        return any(k in s for k in ("server disconnected", "connectionerror",
                                    "connection reset", "broken pipe", "eof occurred"))

    # ------------------------------------------------------------------
    # Session & fighter discovery
    # ------------------------------------------------------------------

    def fetch_active_session(self):
        """
        Query fight_telemetry_sessions for the current active row.
        Populates _session_id, _session_token, _fighter_red/blue_id.
        Returns the raw row dict or None.
        """
        db = self._get_db()
        if not db:
            # Fallback: try edge function
            return self._fetch_active_session_http()
        try:
            res = (db.table("fight_telemetry_sessions")
                     .select("*")
                     .eq("status", "active")
                     .limit(1)
                     .execute())
            if not res.data:
                print("[FighterIDAPI] fetch_active_session: sin sesión activa")
                return None
            row = res.data[0]
            with self._state_lock:
                self._session_id      = row["id"]
                self._session_token   = row.get("session_token")
                self._fighter_red_id  = row.get("fighter_red_id")
                self._fighter_blue_id = row.get("fighter_blue_id")
                # Usar fight_id de la DB si existe — evita FK constraint en ai_fight_results
                if row.get("fight_id"):
                    self._fight_id = row["fight_id"]
            print(f"[FighterIDAPI] sesión activa → id={self._session_id}"
                  f"  fight_id={self._fight_id or '(pendiente)'}")
            return row
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            print(f"[FighterIDAPI] fetch_active_session error: {e}")
            return None

    def _fetch_active_session_http(self):
        """HTTP fallback when supabase-py is unavailable."""
        if not _cfg.API_ENABLED or not _cfg.FIGHTERID_API_KEY:
            return None
        try:
            r = requests.get(
                f"{_cfg.FIGHTERID_EDGE_URL}/vision/get-active-session",
                headers=self._headers(),
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                self._session_token = data.get("session_token")
                self._session_id    = data.get("session_id") or data.get("id")
                print(f"[FighterIDAPI] session_token={self._session_token}")
                return data
            print(f"[FighterIDAPI] fetch_active_session HTTP {r.status_code}")
        except Exception as e:
            print(f"[FighterIDAPI] fetch_active_session HTTP error: {e}")
        return None

    def _load_fighters(self, session_row):
        """
        Load fighter names from fighter_profiles using the IDs stored in
        the session row.  Updates _fighter_red/blue_name in-place.
        """
        db = self._get_db()
        if not db:
            return
        ids = [i for i in [
            session_row.get("fighter_red_id"),
            session_row.get("fighter_blue_id"),
        ] if i]
        if not ids:
            return
        try:
            res = (db.table("fighter_profiles")
                     .select("id, name, full_name, nickname, record, weight_class, gym_id")
                     .in_("id", ids)
                     .execute())
            for f in res.data:
                if f["id"] == session_row.get("fighter_red_id"):
                    self._fighter_red_name    = self._resolve_name(f, "Rojo")
                    self._fighter_red_profile = f
                elif f["id"] == session_row.get("fighter_blue_id"):
                    self._fighter_blue_name    = self._resolve_name(f, "Azul")
                    self._fighter_blue_profile = f
            print(f"[FighterIDAPI] fighters → "
                  f"red={self._fighter_red_name}  blue={self._fighter_blue_name}")
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            print(f"[FighterIDAPI] _load_fighters error: {e}")

    # ------------------------------------------------------------------
    # Fighter profiles — for OfficialSessionDialog
    # ------------------------------------------------------------------

    def list_fighter_profiles(self):
        """
        Returns list of fighter profile dicts for the session dialog.
        Uses SELECT * so it works regardless of which optional columns exist
        in the live DB (gym, total_fights, accuracy, etc.).
        """
        db = self._get_db()
        if not db:
            return []
        try:
            res = (db.table("fighter_profiles")
                     .select("*")
                     .order("name", desc=False)
                     .execute())
            return res.data or []
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            print(f"[FighterIDAPI] list_fighter_profiles error: {e}")
            return []

    def fetch_fight_context(self, fight_id: str) -> dict | None:
        """
        Retorna contexto completo del combate:
          {"fighter_red": {id, name, nickname, record, weight_class, gym},
           "fighter_blue": {...}}

        Intento 1: view fight_full_context (requiere migración SQL aplicada).
        Intento 2: join directo fights ↔ fighter_profiles (funciona sin migración).
        Si ambos fallan: retorna None sin lanzar excepción.

        Actualiza _fighter_red/blue_name y _fighter_red/blue_profile como efecto colateral.
        """
        db = self._get_db()
        if not db or not fight_id:
            return None

        def _build_result(red: dict, blue: dict) -> dict:
            r_name = self._resolve_name(red, "Rojo")
            b_name = self._resolve_name(blue, "Azul")
            with self._state_lock:
                self._fighter_red_name     = r_name
                self._fighter_blue_name    = b_name
                self._fighter_red_id       = red.get("id")  or self._fighter_red_id
                self._fighter_blue_id      = blue.get("id") or self._fighter_blue_id
                self._fighter_red_profile  = red
                self._fighter_blue_profile = blue
            print(f"[FighterIDAPI] fight_context → red={r_name}  blue={b_name}")
            return {
                "fighter_red":  {
                    "id":           red.get("id")           or red.get("fighter_red_id"),
                    "name":         r_name,
                    "nickname":     red.get("nickname")     or red.get("fighter_red_nickname"),
                    "record":       red.get("record")       or red.get("fighter_red_record"),
                    "weight_class": red.get("weight_class") or red.get("fighter_red_weight"),
                    "gym":          red.get("gym")          or red.get("fighter_red_gym"),
                },
                "fighter_blue": {
                    "id":           blue.get("id")           or blue.get("fighter_blue_id"),
                    "name":         b_name,
                    "nickname":     blue.get("nickname")     or blue.get("fighter_blue_nickname"),
                    "record":       blue.get("record")       or blue.get("fighter_blue_record"),
                    "weight_class": blue.get("weight_class") or blue.get("fighter_blue_weight"),
                    "gym":          blue.get("gym")          or blue.get("fighter_blue_gym"),
                },
            }

        # ── Intento 1: fight_full_context view ────────────────────────
        try:
            res = (db.table("fight_full_context")
                     .select("*")
                     .eq("fight_id", fight_id)
                     .limit(1)
                     .execute())
            if res.data:
                row = res.data[0]
                # La view expone columnas planas — convertir a sub-dicts
                red  = {k.replace("fighter_red_",  ""): v
                        for k, v in row.items() if k.startswith("fighter_red_")}
                blue = {k.replace("fighter_blue_", ""): v
                        for k, v in row.items() if k.startswith("fighter_blue_")}
                red["id"]  = row.get("fighter_red_id")
                blue["id"] = row.get("fighter_blue_id")
                return _build_result(red, blue)
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            # View no existe aún — continuar con fallback
        # ── Intento 2: join directo (sin migración) ───────────────────
        try:
            res = (db.table("fights")
                     .select("id, status, "
                             "fighter_red:fighter_profiles!fighter_a_id"
                             "(id, name, full_name, nickname, record, weight_class, gym), "
                             "fighter_blue:fighter_profiles!fighter_b_id"
                             "(id, name, full_name, nickname, record, weight_class, gym)")
                     .eq("id", fight_id)
                     .limit(1)
                     .execute())
            if res.data:
                row  = res.data[0]
                red  = row.get("fighter_red")  or {}
                blue = row.get("fighter_blue") or {}
                return _build_result(red, blue)
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            print(f"[FighterIDAPI] fetch_fight_context fallback error: {e}")

        return None

    def create_fight_session(self, red_id, blue_id, total_rounds=3,
                             model_version="v4.3"):
        """
        Create a new fight_telemetry_sessions row with status='active'.
        Called from OfficialSessionDialog before the session starts.
        fight_id is generated by Supabase (DB default gen_random_uuid()) — the motor
        does NOT invent fight_ids locally.
        Populates _session_id, _session_token, _fight_id, _fighter_red/blue_id.
        Returns the new row dict or None on error.
        """
        db = self._get_db()
        if not db:
            print("[FighterIDAPI] create_fight_session: supabase-py no disponible")
            return None
        # session_token is a local auth token for the motor (not a fight identifier)
        session_token = str(_uuid_mod.uuid4())
        # fight_id intentionally omitted — Supabase generates it via gen_random_uuid() default
        row = {
            "session_token":     session_token,
            "status":            "active",
            "fighter_red_id":    red_id,
            "fighter_blue_id":   blue_id,
            "total_rounds":      total_rounds,
            "model_version":     model_version,
            "hud_connected":     False,
            "vision_connected":  False,
        }
        try:
            res = db.table("fight_telemetry_sessions").insert(row).execute()
            if res.data:
                created = res.data[0]
                with self._state_lock:
                    self._session_id      = created["id"]
                    self._session_token   = created.get("session_token", session_token)
                    # fight_id comes from the DB — never from a local uuid4()
                    self._fight_id        = created.get("fight_id")
                    self._fighter_red_id  = red_id
                    self._fighter_blue_id = blue_id
                print(f"[FighterIDAPI] sesión oficial creada → id={self._session_id}"
                      f"  fight_id={self._fight_id}")
                return created
        except Exception as e:
            if self._is_disconnect(e):
                self._reset_db()
            print(f"[FighterIDAPI] create_fight_session error: {e}")
        return None

    def start_session_test(self):
        """
        Start a local test session for solo training.
        No Supabase session required — but will reuse one if it exists.
        The motor does NOT invent fight_ids — it tries to fetch one from the web.
        """
        self._round_num = 1
        # If no fight_id yet, try to fetch one from an active web session
        if not self._fight_id:
            session_row = self.fetch_active_session()
            if session_row:
                self._load_fighters(session_row)
            else:
                print("[FighterIDAPI] start_session_test: sin fight_id de la web — "
                      "eventos no se enviarán hasta que la web cree una sesión")
        # Default names for test mode
        if not self._fighter_red_name or self._fighter_red_name in ("Rojo", ""):
            self._fighter_red_name = "Peleador"
        payload = {
            "_action":       "session_start",
            "fightId":       self._fight_id,
            "source":        "Fighter ID Vision v4.3",
            "model":         "yolov8-pose",
            "model_version": "v4.3",
            "mode":          "test",
            "fighters":      {"A": self._fighter_red_name, "B": "—"},
        }
        if self._session_token:
            payload["session_token"] = self._session_token
        self._session_queue.append(payload)
        print(f"[FighterIDAPI] Sesión TEST iniciada → fight_id={self._fight_id}")

    def connect_engine(self, session_token):
        """
        Marca vision_connected=true.
        Ruta 1: POST vision-start-session/connect (endpoint real).
        Ruta 2: UPDATE directo en DB (fallback si el edge function falla).
        """
        # ── Ruta 1: POST vision-start-session/connect ─────────────────────
        ok, _ = self._post_vsync("connect", {
            "session_token": session_token,
            "session_id":    self._session_id,
            "engine":        "vision-ai-v1",
            "model_version": "v4.2",
            "timestamp_ms":  int(time.time() * 1000),
        })
        if ok:
            print("[FighterIDAPI] connect-engine OK (vision-start-session/connect)")
            return True
        # ── Ruta 2: DB directo como fallback ──────────────────────────────
        db = self._get_db()
        if db and self._session_id:
            try:
                db.table("fight_telemetry_sessions").update({
                    "vision_connected": True,
                    "last_heartbeat":   "now()",
                }).eq("id", self._session_id).execute()
                print("[FighterIDAPI] connect-engine OK (DB fallback)")
                return True
            except Exception as e:
                if self._is_disconnect(e):
                    self._reset_db()
                print(f"[FighterIDAPI] connect-engine FAILED: {e}")
        return False

    def _create_vision_sync_session(self):
        """
        POST vision-start-session/ — registra el motor en vision_sync_sessions.
        Llamado al inicio de cada sesión para que el HUD sepa que Vision está conectado.
        """
        ok, data = self._post_vsync("", {
            "session_id":    self._session_id,
            "fight_id":      self._fight_id,
            "engine":        "vision-ai-v1",
            "model_version": "v4.2",
            "timestamp_ms":  int(time.time() * 1000),
        })
        print(f"[FighterIDAPI] vision-sync-session {'creada' if ok else 'FAILED'}"
              + (f" → {data.get('id','')}" if ok and data else ""))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self, fight_id, fighter_a_name="Rojo", fighter_b_name="Azul", mode="fight"):
        self._fight_id  = fight_id   # provisional — puede ser sobreescrito por DB en fetch_active_session
        self._round_num = 1

        # 1) Fetch active session from DB (también actualiza self._fight_id si la DB tiene uno)
        session_row = self.fetch_active_session()

        # 2) Load full fighter context — intenta view unificada, fallback a join
        effective_fight_id = self._fight_id or fight_id
        if effective_fight_id:
            ctx = self.fetch_fight_context(effective_fight_id)
        else:
            ctx = None

        # 3) Si no hubo contexto completo, cargar nombres básicos desde session
        if not ctx:
            if session_row:
                self._load_fighters(session_row)
            else:
                self._fighter_red_name  = fighter_a_name
                self._fighter_blue_name = fighter_b_name

        # 4) Crear sync session en vision_sync_sessions
        self._create_vision_sync_session()

        # 4) Registrar motor como conectado en la sesión activa
        if self._session_token:
            self.connect_engine(self._session_token)

        # 5) Queue edge-function ai-strike-ingest/start call
        payload = {
            "_action":        "session_start",
            "fightId":        fight_id,
            "source":         "Fighter ID Vision v4.2",
            "model":          "yolov8-pose",
            "model_version":  "v4.2",
            "fighters": {
                "A": self._fighter_red_name,
                "B": self._fighter_blue_name,
            },
        }
        if self._session_token:
            payload["session_token"] = self._session_token
        self._session_queue.append(payload)
        print(f"[FighterIDAPI] Sesión iniciada → fight_id={fight_id}")

    def end_fight(self, winner, red_stats=None, blue_stats=None, round_results=None):
        if not self._fight_id:
            print("[FighterIDAPI] end_fight: sin fight_id activo")
            return
        payload = {
            "_action":        "fight_end",
            "fightId":        self._fight_id,
            "sessionId":      self._session_id,
            "winner":         _FIGHTER_MAP.get(winner, "draw"),
            "winner_corner":  winner,
            "method":         "decision",
            "model_version":  "v4.2",
            "red_stats":      red_stats      or {},
            "blue_stats":     blue_stats     or {},
            "round_results":  round_results  or {},
            "total_rounds":   3,
            "stats":          {"total_frames": 0, "avg_fps": 0.0, "avg_latency_ms": 0.0},
        }
        if self._session_token:
            payload["session_token"] = self._session_token
        self._session_queue.append(payload)
        print(f"[FighterIDAPI] Pelea finalizada → winner={winner} fight_id={self._fight_id}")
        self._fight_id = None

    def advance_round(self, round_number):
        self._round_num = round_number

    def resolve_fighter(self, track_id):
        """
        Map a corner label ("red" | "blue") to the DB fighter UUID.
        The WEB is the source of truth for fighter IDs — this method
        simply reads what was populated by start_session() / fetch_active_session().
        """
        if track_id == "red":
            return self._fighter_red_id
        else:
            return self._fighter_blue_id

    def send_event(self, fighter_id, confidence):
        """
        Convenience method: send a single strike event to the web backend.
        fighter_id must be a DB UUID obtained via resolve_fighter().
        The motor only sends — it never invents IDs.
        """
        if not self._fight_id:
            print("[FighterIDAPI] send_event: sin fight_id activo — evento descartado")
            return
        try:
            requests.post(
                f"{self._base_url()}/event",
                json={
                    "session_id": self._session_id,
                    "fight_id":   self._fight_id,
                    "fighter_id": fighter_id,
                    "type":       "strike",
                    "confidence": confidence,
                    "timestamp":  time.time(),
                },
                headers=self._headers(),
                timeout=5,
            )
        except Exception as e:
            print(f"[FighterIDAPI] send_event error: {e}")

    def listen_fight_changes(self):
        """
        Subscribe to realtime broadcast 'fight_active' from the web.
        When fight_id changes, automatically re-sync the session so the motor
        is always aligned with the web — no local state invented.
        Starts a daemon thread so it doesn't block the main loop.
        """
        def _run():
            db = self._get_db()
            if not db:
                print("[FighterIDAPI] listen_fight_changes: supabase-py no disponible")
                return
            try:
                def handle(payload):
                    new_fight = (payload.get("fight_id")
                                 or payload.get("payload", {}).get("fight_id"))
                    if new_fight and new_fight != self._fight_id:
                        print(f"[REALTIME] fight_id cambió → {new_fight}")
                        self.start_session(new_fight)

                channel = db.channel("fight_sync")
                channel.on("broadcast", {"event": "fight_active"}, handle)
                channel.subscribe()
                print("[FighterIDAPI] realtime fight_sync suscrito")
                # Keep thread alive while subscription is active
                while True:
                    time.sleep(30)
            except Exception as e:
                msg = str(e)
                if any(k in msg.lower() for k in ("sync client", "async client", "async", "realtime", "not available")):
                    pass  # supabase-py sync client doesn't support realtime — non-critical
                else:
                    print(f"[FighterIDAPI] listen_fight_changes error: {e}")

        t = threading.Thread(target=_run, daemon=True, name="FighterIDRealtime")
        t.start()

    def send(self, fighter_id, punch_type, speed, extension, hit,
             face_hit, body_hit, elbow_angle=0.0):
        with self._state_lock:
            fight_id      = self._fight_id
            session_id    = self._session_id
            session_token = self._session_token
            round_num     = self._round_num
            db_fighter_id = (self._fighter_red_id
                             if fighter_id == "red"
                             else self._fighter_blue_id)

        if not fight_id:
            return

        confidence   = min(max(speed / 25.0, 0.05), 1.0)
        fighter_slot = _FIGHTER_MAP.get(fighter_id, "A")
        strike_type  = _PUNCH_TYPE_MAP.get(punch_type.lower(), "other")
        event_type   = "strike_connected" if hit else "strike_attempted"

        evt = {
            # DB fields (used by _send_event_to_db)
            "_session_id":    session_id,
            "_fighter_id":    db_fighter_id,
            "_fighter_corner": fighter_id,          # "red" | "blue"
            # Edge-function fields (ai-strike-ingest/event)
            "sessionId":      session_id,
            "fightId":        fight_id,
            "round":          round_num,
            "timestamp_ms":   int(time.time() * 1000),
            "fighter":        fighter_slot,
            "event":          event_type,
            "strike_type":    strike_type,
            "confidence":     round(confidence, 3),
            "model_version":  "v4.2",
            "metadata": {
                "speed_ms":      round(speed, 3),
                "extension_m":   round(extension, 3),
                "face_hit":      face_hit,
                "body_hit":      body_hit,
                "elbow_angle":   round(elbow_angle, 1),
                "original_type": punch_type,
            },
        }
        if session_token:
            evt["session_token"] = session_token
        self._queue.append(evt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {_cfg.FIGHTERID_API_KEY}",
            "Content-Type":  "application/json",
            "apikey":         _cfg.FIGHTERID_API_KEY,
        }

    def _base_url(self):
        return _cfg.FIGHTERID_API_URL         # .../functions/v1/ai-strike-ingest

    def _vsync_url(self):
        return f"{_cfg.FIGHTERID_EDGE_URL}/vision-start-session"  # .../functions/v1/vision-start-session

    def _post(self, path, body, timeout=5):
        if not _cfg.API_ENABLED or not _cfg.FIGHTERID_API_KEY:
            return False, {}
        try:
            r = requests.post(
                f"{self._base_url()}/{path}",
                json=body,
                headers=self._headers(),
                timeout=timeout,
            )
            ok = r.status_code < 300
            try:
                data = r.json()
            except Exception:
                data = {}
            if not ok:
                print(f"[FighterIDAPI] POST /{path} HTTP {r.status_code}: {data}")
            return ok, data
        except Exception as e:
            print(f"[FighterIDAPI] POST /{path} error: {e}")
            return False, {}

    def _post_vsync(self, subpath, body, timeout=5):
        """POST a vision-start-session/<subpath>. subpath='' para la raíz."""
        if not _cfg.API_ENABLED or not _cfg.FIGHTERID_API_KEY:
            return False, {}
        url = self._vsync_url() + (f"/{subpath}" if subpath else "")
        try:
            r = requests.post(url, json=body, headers=self._headers(), timeout=timeout)
            ok = r.status_code < 300
            try:
                data = r.json()
            except Exception:
                data = {}
            if not ok:
                print(f"[FighterIDAPI] POST vision-start-session/{subpath} "
                      f"HTTP {r.status_code}: {data}")
            return ok, data
        except Exception as e:
            print(f"[FighterIDAPI] POST vision-start-session/{subpath} error: {e}")
            return False, {}

    def _send_event_to_db(self, evt):
        """
        Insert a strike event directly into fight_telemetry_events.
        Falls back to the /event edge function if the DB client is
        unavailable or if there is no session_id yet.
        """
        db         = self._get_db()
        session_id = evt.get("_session_id") or self._session_id

        if db and session_id:
            meta = evt.get("metadata", {})
            try:
                db.table("fight_telemetry_events").insert({
                    "session_id":     session_id,
                    "fighter_id":     evt.get("_fighter_id"),
                    "fighter_corner": evt.get("_fighter_corner", "red"),
                    "round":          evt.get("round", self._round_num),
                    "strike_type":    evt.get("strike_type", "other"),
                    "event_type":     evt.get("event", "strike_attempted"),
                    "confidence":     evt.get("confidence", 0.0),
                    "timestamp_video": evt.get("timestamp_ms", 0) / 1000.0,
                    "speed_ms":       meta.get("speed_ms"),
                    "extension_m":    meta.get("extension_m"),
                    "face_hit":       meta.get("face_hit", False),
                    "body_hit":       meta.get("body_hit", False),
                    "elbow_angle":    meta.get("elbow_angle"),
                    "model_version":  evt.get("model_version", "v4.2"),
                }).execute()
                self.sent_ok += 1
                return
            except Exception as e:
                if self._is_disconnect(e):
                    self._reset_db()
                err_str = str(e.args[0]) if (hasattr(e, 'args') and e.args) else str(e)
                # PGRST204 = column not found in schema cache → run migration
                if "PGRST204" in err_str or "event_type" in err_str:
                    print(f"[FighterIDAPI] DB insert error: {e}")
                    print("[FighterIDAPI] ACCION REQUERIDA: ejecuta supabase_migration_event_type.sql")
                    print("[FighterIDAPI] en el SQL Editor de Supabase para agregar la columna event_type")
                else:
                    print(f"[FighterIDAPI] DB insert error: {e}")

        # Fallback: strip private keys and send via edge function
        edge_evt = {k: v for k, v in evt.items() if not k.startswith("_")}
        ok, _ = self._post("event", edge_evt)
        if ok:
            self.sent_ok  += 1
        else:
            self.sent_err += 1

    # ------------------------------------------------------------------
    # Background workers
    # ------------------------------------------------------------------

    def _worker(self):
        while True:
            if not self._queue:
                time.sleep(0.02)
                continue
            evt = self._queue.popleft()
            self._send_event_to_db(evt)

    def _session_worker(self):
        # ─────────────────────────────────────────────────────────────────
        # Endpoints correctos (ai-strike-ingest v2.1):
        #   session_start → POST ai-strike-ingest/start      ← CORRECTO
        #   fight_end     → POST ai-strike-ingest/stop + /end
        # NO usar: /vision-start-session  /heartbeat  /connect-engine
        # ─────────────────────────────────────────────────────────────────
        while True:
            if not self._session_queue:
                time.sleep(0.1)
                continue
            payload = self._session_queue.popleft()
            action  = payload.pop("_action", "")

            if action == "session_start":
                # POST ai-strike-ingest/start — inicia sesión de inferencia
                ok, data = self._post("start", payload)   # ← /start no /vision-start-session
                if ok:
                    self._session_id = (data.get("sessionId")
                                        or data.get("session_id")
                                        or self._session_id)
                    # Read fight_id and fighter IDs from web response (source of truth)
                    if data.get("fight_id"):
                        self._fight_id = data["fight_id"]
                    fighters = data.get("fighters", {})
                    if fighters.get("red", {}).get("id"):
                        self._fighter_red_id = fighters["red"]["id"]
                    if fighters.get("blue", {}).get("id"):
                        self._fighter_blue_id = fighters["blue"]["id"]
                    print(f"[SYNC] Session OK {self._session_id}"
                          + (f"  fight_id={self._fight_id}" if self._fight_id else "")
                          + (f"  red={self._fighter_red_id}" if self._fighter_red_id else "")
                          + (f"  blue={self._fighter_blue_id}" if self._fighter_blue_id else ""))
                else:
                    print(f"[FighterIDAPI] session/start FAILED"
                          + (f" session_id={self._session_id}" if self._session_id else "")
                          + (f" resp={data}" if data else ""))

            elif action == "fight_end":
                # POST ai-strike-ingest/stop → /end
                if payload.get("sessionId"):
                    self._post("stop", {
                        "sessionId":     payload["sessionId"],
                        "session_token": payload.get("session_token"),
                        "stats":         payload.get("stats", {}),
                    })
                ok, _ = self._post("end", payload, timeout=10)
                print(f"[FighterIDAPI] fight/end {'OK' if ok else 'FAILED'}"
                      f" → winner={payload.get('winner_corner')}")

    def _heartbeat_worker(self):
        while True:
            time.sleep(_HEARTBEAT_INTERVAL)
            with self._state_lock:
                fight_id      = self._fight_id
                session_id    = self._session_id
                session_token = self._session_token

            if not fight_id:
                continue

            db = self._get_db()
            if db and session_id:
                # Direct DB update — fastest path, no edge function overhead
                try:
                    db.table("fight_telemetry_sessions").update({
                        "vision_connected": True,
                        "last_heartbeat":   "now()",
                    }).eq("id", session_id).execute()
                    continue
                except Exception as e:
                    if self._is_disconnect(e):
                        self._reset_db()
                    print(f"[FighterIDAPI] heartbeat DB error: {e}")

            # Fallback: POST vision-start-session/telemetry
            self._post_vsync("telemetry", {
                "session_id":    session_id,
                "fight_id":      fight_id,
                "session_token": session_token,
                "engine":        "vision-ai-v1",
                "timestamp_ms":  int(time.time() * 1000),
            })
