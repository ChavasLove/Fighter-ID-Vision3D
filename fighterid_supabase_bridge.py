"""
FighterID Vision — Supabase Bridge v1.1
Reemplaza la clase FighterIDAPI de main.py.
"""
import threading, time
from collections import deque
import requests

_PUNCH_TYPE_MAP = {
    "jab": "jab", "cross": "cross", "hook": "hook",
    "uppercut": "uppercut", "overhand": "other",
    "bodyshot": "body_kick", "unknown": "other",
}
_FIGHTER_MAP = {"red": "A", "blue": "B", "test": "A"}

_HEARTBEAT_INTERVAL = 3  # seconds


class FighterIDAPI:
    def __init__(self):
        self._queue = deque(maxlen=500)
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
        self.sent_ok       = 0
        self.sent_err      = 0
        self._session_id   = None
        self._session_token = None
        self._fight_id     = None
        self._round_num    = 1

    @property
    def fight_id(self): return self._fight_id or ""
    @fight_id.setter
    def fight_id(self, v): self._fight_id = v

    @property
    def round_number(self): return self._round_num
    @round_number.setter
    def round_number(self, v): self._round_num = v

    # ------------------------------------------------------------------ #
    #  HUD session sync                                                    #
    # ------------------------------------------------------------------ #

    def fetch_active_session(self):
        """GET /vision/get-active-session — returns session_token str or None."""
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
                token = r.json().get("session_token")
                if token:
                    print(f"[FighterIDAPI] session_token={token}")
                    return token
            print(f"[FighterIDAPI] fetch_active_session: no token ({r.status_code})")
        except Exception as e:
            print(f"[FighterIDAPI] fetch_active_session error: {e}")
        return None

    def connect_engine(self, session_token):
        """POST /vision/connect-engine — registers this engine against the HUD session."""
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
            print(f"[FighterIDAPI] connect-engine {'OK' if ok else 'FAILED'}")
            return ok
        except Exception as e:
            print(f"[FighterIDAPI] connect-engine error: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def start_session(self, fight_id, fighter_a_name="Rojo", fighter_b_name="Azul", mode="fight"):
        self._fight_id  = fight_id
        self._round_num = 1

        # Sync with HUD session
        token = self.fetch_active_session()
        if token:
            self._session_token = token
            self.connect_engine(token)

        payload = {
            "_action":        "session_start",
            "fightId":        fight_id,
            "session_token":  self._session_token,
            "source":         "Fighter ID Vision v4.2",
            "model":          "yolov8-pose",
            "model_version":  "v4.2",
            "fighters":       {"A": fighter_a_name, "B": fighter_b_name},
        }
        self._session_queue.append(payload)
        print(f"[FighterIDAPI] Sesión iniciada → fight_id={fight_id}")

    def end_fight(self, winner, red_stats=None, blue_stats=None, round_results=None):
        if not self._fight_id:
            print("[FighterIDAPI] end_fight: sin fight_id activo"); return
        payload = {
            "_action":        "fight_end",
            "fightId":        self._fight_id,
            "sessionId":      self._session_id,
            "session_token":  self._session_token,
            "winner":         _FIGHTER_MAP.get(winner, "draw"),
            "winner_corner":  winner,
            "method":         "decision",
            "model_version":  "v4.2",
            "red_stats":      red_stats  or {},
            "blue_stats":     blue_stats or {},
            "round_results":  round_results or {},
            "total_rounds":   3,
            "stats":          {"total_frames": 0, "avg_fps": 0.0, "avg_latency_ms": 0.0},
        }
        self._session_queue.append(payload)
        print(f"[FighterIDAPI] Pelea finalizada → winner={winner} fight_id={self._fight_id}")
        self._fight_id = None

    def advance_round(self, round_number):
        self._round_num = round_number

    def send(self, fighter_id, punch_type, speed, extension, hit, face_hit, body_hit, elbow_angle=0.0):
        if not self._fight_id:
            return
        confidence   = min(max(speed / 25.0, 0.05), 1.0)
        fighter_slot = _FIGHTER_MAP.get(fighter_id, "A")
        strike_type  = _PUNCH_TYPE_MAP.get(punch_type.lower(), "other")
        event_type   = "strike_connected" if hit else "strike_attempted"
        evt = {
            "fightId":        self._fight_id,
            "session_token":  self._session_token,
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
        self._queue.append(evt)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

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
            r = requests.post(f"{self._base_url()}/{path}", json=body,
                              headers=self._headers(), timeout=timeout)
            ok = r.status_code < 300
            try:
                data = r.json()
            except Exception:
                data = {}
            return ok, data
        except Exception as e:
            print(f"[FighterIDAPI] POST /{path} error: {e}")
            return False, {}

    # ------------------------------------------------------------------ #
    #  Background workers                                                  #
    # ------------------------------------------------------------------ #

    def _worker(self):
        while True:
            if not self._queue: time.sleep(0.02); continue
            evt = self._queue.popleft()
            ok, _ = self._post("event", evt)
            if ok: self.sent_ok  += 1
            else:  self.sent_err += 1

    def _session_worker(self):
        while True:
            if not self._session_queue: time.sleep(0.1); continue
            payload = self._session_queue.popleft()
            action  = payload.pop("_action", "")
            if action == "session_start":
                ok, data = self._post("start", payload)
                if ok:
                    self._session_id = data.get("sessionId") or data.get("session_id")
                print(f"[FighterIDAPI] session/start {'OK' if ok else 'FAILED'}"
                      + (f" session_id={self._session_id}" if self._session_id else ""))
            elif action == "fight_end":
                if payload.get("sessionId"):
                    self._post("stop", {"sessionId": payload["sessionId"],
                                        "session_token": payload.get("session_token"),
                                        "stats": payload.get("stats", {})})
                ok, _ = self._post("end", payload, timeout=10)
                print(f"[FighterIDAPI] fight/end {'OK' if ok else 'FAILED'}"
                      f" → winner={payload.get('winner_corner')}")

    def _heartbeat_worker(self):
        while True:
            time.sleep(_HEARTBEAT_INTERVAL)
            if not self._fight_id:
                continue
            self._post("heartbeat", {
                "fightId":       self._fight_id,
                "session_token": self._session_token,
                "engine":        "vision-ai-v1",
                "timestamp_ms":  int(time.time() * 1000),
            })
