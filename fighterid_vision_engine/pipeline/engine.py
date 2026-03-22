"""
FighterID Vision Engine — Motor principal (VisionMotorV1 + FighterIDAPI)

Contrato:
  - fight_id viene SIEMPRE de la API web (--fight-id o FIGHT_ID env var)
  - session_id, fight_id y fighter UUIDs vienen de POST /start
  - El motor NUNCA genera UUIDs localmente
  - Camera mapping explícito logueado al arrancar para diagnóstico

Extraído y modularizado desde vision_motor_v1.py.
"""

import threading
import time

import cv2
import numpy as np
import requests

from fighterid_vision_engine.camera.capture import CameraStream
from fighterid_vision_engine.detection.pose import PoseDetector
from fighterid_vision_engine.detection.tracker import SimpleTracker
from fighterid_vision_engine.pipeline.strike import StrikeDetector
from fighterid_vision_engine.pipeline.recorder import VideoRecorder
from fighterid_vision_engine.config.settings import (
    FIGHTERID_API_URL,
    FIGHTERID_API_KEY,
    DEVICE_ID,
    API_ENABLED,
)


def discover_fight_id() -> "str | None":
    """
    Autodescubre el fight_id consultando fight_telemetry_sessions en Supabase.

    Orden de intentos:
      1. REST directo → fight_telemetry_sessions?status=eq.active
      2. Edge function → /vision/get-active-session

    Retorna el fight_id (str) de la sesión activa más reciente, o None si no
    hay ninguna sesión activa o si API_ENABLED=false.
    """
    from fighterid_vision_engine.config.settings import (
        SUPABASE_URL, SUPABASE_ANON_KEY,
        FIGHTERID_EDGE_URL, API_ENABLED as _api_enabled,
    )
    if not _api_enabled:
        return None

    anon_headers = {
        "apikey":        SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    }

    # Intento 1: REST directo
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/fight_telemetry_sessions",
            headers=anon_headers,
            params={
                "select": "fight_id",
                "status": "eq.active",
                "order":  "created_at.desc",
                "limit":  "1",
            },
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            if data and data[0].get("fight_id"):
                return data[0]["fight_id"]
        else:
            print(f"[DISCOVER] REST → HTTP {r.status_code}")
    except Exception as e:
        print(f"[DISCOVER] REST error: {e}")

    # Intento 2: edge function fallback
    try:
        r = requests.get(
            f"{FIGHTERID_EDGE_URL}/vision/get-active-session",
            headers={
                "apikey":        FIGHTERID_API_KEY,
                "Authorization": f"Bearer {FIGHTERID_API_KEY}",
            },
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            fid = data.get("fight_id") or data.get("id")
            if fid:
                return fid
        else:
            print(f"[DISCOVER] edge function → HTTP {r.status_code}")
    except Exception as e:
        print(f"[DISCOVER] edge function error: {e}")

    return None


# ══════════════════════════════════════════════════════════════════
#  FIGHTER ID API — consume la web, no inventa datos
# ══════════════════════════════════════════════════════════════════
class FighterIDAPI:
    """
    Contrato: la WEB es dueña de fight_id y fighters.
    El motor solo llama /start, recibe los IDs, y envía /event.
    """

    def __init__(self, base_url: str = FIGHTERID_API_URL):
        self.base_url   = base_url
        self.session_id = None   # viene de /start
        self.fight_id   = None   # viene de /start
        self.red        = None   # UUID rojo — viene de /start
        self.blue       = None   # UUID azul — viene de /start
        self._hb_running = False  # arranca en start_session(), para en stop_heartbeat()
        # Diagnóstico al arrancar — permite detectar URLs mal configuradas antes
        # de intentar conectar y recibir 'Invalid URL' o errores crípticos.
        print(f"[CONFIG] API_URL     = {self.base_url}")
        print(f"[CONFIG] API_ENABLED = {API_ENABLED}")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {FIGHTERID_API_KEY}",
            "Content-Type":  "application/json",
            "apikey":         FIGHTERID_API_KEY,
        }

    def start_session(self, fight_id: str) -> None:
        """
        POST /start → obtiene session_id, fight_id y fighter UUIDs desde la web.
        Lanza RuntimeError si el backend no responde correctamente.
        """
        if not API_ENABLED:
            print("[API] API_ENABLED=false — modo sin conexión (sin enviar eventos)")
            self.fight_id = fight_id
            return

        resp = requests.post(
            f"{self.base_url}/start",
            json={
                "fight_id":  fight_id,
                "device_id": DEVICE_ID,
                "cameras":   [0, 1, 2],
            },
            headers=self._headers(),
            timeout=10,
        ).json()

        if "session_id" not in resp:
            raise RuntimeError(f"[ERROR] start_session failed: {resp}")

        self.session_id = resp["session_id"]
        self.fight_id   = resp["fight_id"]

        fighters    = resp.get("fighters", {})
        self.red    = fighters.get("red",  {}).get("id")
        self.blue   = fighters.get("blue", {}).get("id")

        print(f"[SYNC OK] fight={self.fight_id}  session={self.session_id}")
        print(f"[FIGHTERS] red={self.red}  blue={self.blue}")

        # Arrancar heartbeat — POST /heartbeat cada 3s mientras la sesión está activa
        self._hb_running = True
        threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="FighterIDHeartbeat",
        ).start()
        print("[HEARTBEAT] loop iniciado")

    def _heartbeat_loop(self) -> None:
        """POST /heartbeat cada 3s — mantiene last_heartbeat actualizado en la web."""
        while self._hb_running:
            try:
                requests.post(
                    f"{self.base_url}/heartbeat",
                    json={
                        "fight_id":  self.fight_id,
                        "device_id": DEVICE_ID,
                    },
                    headers=self._headers(),
                    timeout=3,
                )
            except Exception as e:
                print(f"[HEARTBEAT] Error: {e}")
            time.sleep(3)

    def stop_heartbeat(self) -> None:
        """Detiene el loop de heartbeat — llamado desde VisionMotorV1.stop()."""
        self._hb_running = False

    def send_event(self, fighter_id: str, confidence: float) -> None:
        """POST /event — fire-and-forget en hilo daemon."""
        if not self.fight_id or not API_ENABLED:
            return
        payload = {
            "session_id": self.session_id,
            "fight_id":   self.fight_id,
            "fighter_id": fighter_id,
            "type":       "strike",
            "confidence": round(confidence, 3),
            "timestamp":  time.time(),
        }
        threading.Thread(
            target=self._post_event,
            args=(payload,),
            daemon=True,
        ).start()

    def _post_event(self, payload: dict) -> None:
        try:
            r = requests.post(
                f"{self.base_url}/event",
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
            print(f"[EVENT] OK → status={r.status_code}  fighter={payload.get('fighter_id')}")
        except Exception as e:
            print(f"[EVENT] Error enviando: {e}")

    def resolve_fighter(self, track_id: str):
        """Mapea 'red'/'blue' → UUID de la DB. Los IDs vienen de la web."""
        return self.red if track_id == "red" else self.blue


# ══════════════════════════════════════════════════════════════════
#  VISION MOTOR V1 — orquestador principal
# ══════════════════════════════════════════════════════════════════
class VisionMotorV1:
    """
    Motor de visión V1 estable.

    Flujo:
      1. Recibe fight_id de CLI / env (nunca generado localmente)
      2. start_session(fight_id) → session_id + fighter UUIDs desde la web
      3. Abre cámaras con camera_map explícito
      4. Bucle: detecta pose → asigna esquinas → detecta golpe → POST /event
      5. Graba video con fight_id como nombre de archivo
    """

    def __init__(self, fight_id: str,
                 cam_a: int = 0, cam_b: int = 1, cam_c: int = 2,
                 show: bool = False):
        self.camera_map = {"A": cam_a, "B": cam_b, "C": cam_c}
        print(f"[CAM MAP] {self.camera_map}")

        self._fight_id = fight_id
        self._show     = show
        self.api       = FighterIDAPI()
        self.detector  = PoseDetector()
        self.tracker   = SimpleTracker()
        self.strikes   = StrikeDetector()
        self.recorder  = None
        self._streams: dict = {}
        self._running  = False

    def start(self) -> None:
        print(f"[MOTOR] Iniciando sesión → fight_id={self._fight_id}")
        self.api.start_session(self._fight_id)

        for role, idx in self.camera_map.items():
            if idx is not None:
                stream = CameraStream(idx).start()
                self._streams[role] = stream
                print(f"[CAM {role}] idx={idx} stream activo")

        if "A" not in self._streams or not self._streams["A"].is_open():
            raise RuntimeError("[MOTOR] Cámara A no disponible — abortando")

        self.recorder = VideoRecorder(self.api.fight_id, round_num=1)
        self._running = True

        print("[MOTOR] Bucle de detección iniciado — Ctrl+C para detener")
        self._loop()

    def _loop(self) -> None:
        fps_frames       = 0
        fps_personas_sum = 0   # acumula detecciones por frame para calcular promedio
        fps_t0           = time.time()

        while self._running:
            frame, ts = self._streams["A"].read()
            if frame is None:
                time.sleep(0.01)
                continue

            persons = self.detector.infer(frame)
            roles   = self.tracker.assign(persons)

            self.recorder.write(frame)

            for corner in ("red", "blue"):
                person   = roles.get(corner)
                opponent = roles.get("blue" if corner == "red" else "red")
                if person is None:
                    continue
                hit, speed, conf = self.strikes.detect(corner, person, opponent)
                if hit:
                    fighter_id = self.api.resolve_fighter(corner)
                    print(f"[EVENT] fighter={fighter_id}  corner={corner}"
                          f"  speed={speed:.2f}m/s  conf={conf:.2f}")
                    self.api.send_event(fighter_id, conf)

            if self._show:
                display = self._annotate(frame, roles, len(persons))
                cv2.imshow("FighterID Vision", display)
                if cv2.waitKey(1) & 0xFF == 27:   # ESC para salir
                    self._running = False

            fps_frames       += 1
            fps_personas_sum += len(persons)
            if time.time() - fps_t0 >= 5.0:
                elapsed  = time.time() - fps_t0
                fps      = fps_frames / elapsed
                avg_p    = fps_personas_sum / fps_frames
                # personas_avg: promedio de cuerpos detectados por frame en los últimos 5s
                # personas_now: conteo del frame actual (puede ser 0 entre detecciones)
                print(f"[FPS] {fps:.1f}  personas_avg={avg_p:.1f}  personas_now={len(persons)}")
                fps_frames       = 0
                fps_personas_sum = 0
                fps_t0           = time.time()

    def _annotate(self, frame: np.ndarray, roles: dict,
                  n_persons: int) -> np.ndarray:
        """Dibuja bboxes de esquinas y stats sobre el frame. No modifica el original."""
        disp   = frame.copy()
        COLORS = {"red": (0, 0, 255), "blue": (255, 0, 0)}
        for corner, person in roles.items():
            if person is None:
                continue
            x1, y1, x2, y2 = [int(v) for v in person["bbox"]]
            color = COLORS.get(corner, (0, 255, 0))
            cv2.rectangle(disp, (x1, y1), (x2, y2), color, 2)
            cv2.putText(disp, corner.upper(), (x1, max(y1 - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(disp, f"personas={n_persons}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return disp

    def stop(self) -> None:
        self.api.stop_heartbeat()
        self._running = False
        if self._show:
            cv2.destroyAllWindows()
        if self.recorder:
            self.recorder.stop()
        for role, stream in self._streams.items():
            stream.stop()
            print(f"[CAM {role}] cerrada")
        print("[MOTOR] Detenido")
