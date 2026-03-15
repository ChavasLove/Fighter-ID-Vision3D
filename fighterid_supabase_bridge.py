"""
FighterID Vision — Supabase Bridge v2.0
Reemplaza la clase FighterIDAPI de main.py.

Flujo de datos:
  start_session()
    → GET  fight_telemetry_sessions (status=active)
    → GET  fighter_profiles (red + blue)
    → POST vision/connect-engine  (vision_connected=true)
    → POST /start  (edge function)

  send()  [por cada golpe detectado]
    → INSERT fight_telemetry_events  (directo a DB)
    → fallback: POST /event  (edge function)

  _heartbeat_worker()  [cada 3s mientras hay pelea]
    → UPDATE fight_telemetry_sessions.vision_connected / last_heartbeat
    → fallback: POST /heartbeat  (edge function)

  end_fight()
    → POST /stop + /end  (edge function)
"""

import threading
import time
from collections import deque

import requests

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

        # Session state
        self._db          = None          # supabase client (lazy)
        self._session_id  = None          # fight_telemetry_sessions.id (uuid)
        self._session_token = None        # fight_telemetry_sessions.session_token
        self._fight_id    = None          # fight_telemetry_sessions.fight_id
        self._round_num   = 1

        # Fighter state (loaded from fighter_profiles)
        self._fighter_red_id   = None
        self._fighter_blue_id  = None
        self._fighter_red_name  = "Rojo"
        self._fighter_blue_name = "Azul"

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
            import main as m
            if not m.SUPABASE_URL or not m.SUPABASE_ANON_KEY:
                return None
            self._db = _supa_create(m.SUPABASE_URL, m.SUPABASE_ANON_KEY)
        except Exception as e:
            print(f"[FighterIDAPI] supabase client init error: {e}")
        return self._db

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
            self._session_id    = row["id"]
            self._session_token = row.get("session_token")
            self._fighter_red_id  = row.get("fighter_red_id")
            self._fighter_blue_id = row.get("fighter_blue_id")
            print(f"[FighterIDAPI] sesión activa → id={self._session_id}")
            return row
        except Exception as e:
            print(f"[FighterIDAPI] fetch_active_session error: {e}")
            return None

    def _fetch_active_session_http(self):
        """HTTP fallback when supabase-py is unavailable."""
        import main as m
        if not m.API_ENABLED or not m.FIGHTERID_API_KEY:
            return None
        try:
            r = requests.get(
                f"{m.FIGHTERID_EDGE_URL}/vision/get-active-session",
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
                     .select("id,name")
                     .in_("id", ids)
                     .execute())
            for f in res.data:
                if f["id"] == session_row.get("fighter_red_id"):
                    self._fighter_red_name = f.get("name", "Rojo")
                elif f["id"] == session_row.get("fighter_blue_id"):
                    self._fighter_blue_name = f.get("name", "Azul")
            print(f"[FighterIDAPI] fighters → "
                  f"red={self._fighter_red_name}  blue={self._fighter_blue_name}")
        except Exception as e:
            print(f"[FighterIDAPI] _load_fighters error: {e}")

    def connect_engine(self, session_token):
        """
        POST /vision/connect-engine — sets vision_connected=true in
        fight_telemetry_sessions so the HUD shows VISION ENGINE ONLINE.
        """
        import main as m
        if not m.API_ENABLED or not m.FIGHTERID_API_KEY:
            return False
        try:
            r = requests.post(
                f"{m.FIGHTERID_EDGE_URL}/vision/connect-engine",
                json={"session_token": session_token, "engine": "vision-ai-v1"},
                headers=self._headers(),
                timeout=5,
            )
            ok = r.status_code < 300
            if ok:
                print(f"[FighterIDAPI] connect-engine OK")
            else:
                try:
                    body = r.json()
                except Exception:
                    body = r.text[:200]
                print(f"[FighterIDAPI] connect-engine FAILED HTTP {r.status_code}: {body}")
            return ok
        except Exception as e:
            print(f"[FighterIDAPI] connect-engine error: {e}")
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self, fight_id, fighter_a_name="Rojo", fighter_b_name="Azul", mode="fight"):
        self._fight_id  = fight_id
        self._round_num = 1

        # 1) Fetch active session from DB
        session_row = self.fetch_active_session()

        # 2) Load real fighter names (overrides caller-supplied defaults)
        if session_row:
            self._load_fighters(session_row)
        else:
            self._fighter_red_name  = fighter_a_name
            self._fighter_blue_name = fighter_b_name

        # 3) Register this engine with the HUD session
        if self._session_token:
            self.connect_engine(self._session_token)

        # 4) Queue edge-function /start call
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

    def send(self, fighter_id, punch_type, speed, extension, hit,
             face_hit, body_hit, elbow_angle=0.0):
        if not self._fight_id:
            return

        confidence   = min(max(speed / 25.0, 0.05), 1.0)
        fighter_slot = _FIGHTER_MAP.get(fighter_id, "A")
        strike_type  = _PUNCH_TYPE_MAP.get(punch_type.lower(), "other")
        event_type   = "strike_connected" if hit else "strike_attempted"

        # Map corner → DB fighter UUID
        db_fighter_id = (self._fighter_red_id
                         if fighter_id == "red"
                         else self._fighter_blue_id)

        evt = {
            # DB fields (used by _send_event_to_db)
            "_session_id":    self._session_id,
            "_fighter_id":    db_fighter_id,
            "_fighter_corner": fighter_id,          # "red" | "blue"
            # Edge-function / legacy fields
            "fightId":        self._fight_id,
            "round":          self._round_num,
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
        if self._session_token:
            evt["session_token"] = self._session_token
        self._queue.append(evt)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self):
        import main as m
        return {
            "Authorization": f"Bearer {m.FIGHTERID_API_KEY}",
            "Content-Type":  "application/json",
            "apikey":         m.FIGHTERID_API_KEY,
        }

    def _base_url(self):
        import main as m
        return m.FIGHTERID_API_URL

    def _post(self, path, body, timeout=5):
        import main as m
        if not m.API_ENABLED or not m.FIGHTERID_API_KEY:
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
                err = e
                if hasattr(e, 'args') and e.args:
                    err_str = str(e.args[0])
                else:
                    err_str = str(e)
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
        while True:
            if not self._session_queue:
                time.sleep(0.1)
                continue
            payload = self._session_queue.popleft()
            action  = payload.pop("_action", "")

            if action == "session_start":
                ok, data = self._post("start", payload)
                if ok:
                    self._session_id = (data.get("sessionId")
                                        or data.get("session_id")
                                        or self._session_id)
                    print(f"[FighterIDAPI] session/start OK"
                          + (f" session_id={self._session_id}" if self._session_id else ""))
                else:
                    print(f"[FighterIDAPI] session/start FAILED"
                          + (f" session_id={self._session_id}" if self._session_id else "")
                          + (f" resp={data}" if data else ""))

            elif action == "fight_end":
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
            if not self._fight_id:
                continue

            db = self._get_db()
            if db and self._session_id:
                # Direct DB update — fastest path, no edge function overhead
                try:
                    db.table("fight_telemetry_sessions").update({
                        "vision_connected": True,
                        "last_heartbeat":   "now()",
                    }).eq("id", self._session_id).execute()
                    continue
                except Exception as e:
                    print(f"[FighterIDAPI] heartbeat DB error: {e}")

            # Fallback: edge function
            self._post("heartbeat", {
                "fightId":       self._fight_id,
                "session_token": self._session_token,
                "engine":        "vision-ai-v1",
                "timestamp_ms":  int(time.time() * 1000),
            })
