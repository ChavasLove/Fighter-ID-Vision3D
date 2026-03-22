"""
FighterID Vision Motor V1 — Motor estable de detección de golpes

Contrato:
  - fight_id viene SIEMPRE de la API web (--fight-id o FIGHT_ID env var)
  - session_id, fight_id y fighter UUIDs vienen de POST /start
  - El motor NUNCA genera UUIDs localmente
  - Camera mapping explícito con print al arrancar
  - Logs claros en consola para debug en vivo

Uso:
  python vision_motor_v1.py --fight-id "abc-123" --cam-a 0 --cam-b 1 --cam-c 2
  FIGHT_ID="abc-123" python vision_motor_v1.py

Checklist de validación:
  [GPU] torch-directml → AMD GPU
  [CAM MAP] {'A': 0, 'B': 1, 'C': 2}
  [ONNX] Cargado — providers=[DmlExecutionProvider]
  [SYNC OK] fight=<uuid> session=<uuid>
  [FIGHTERS] red=<uuid>  blue=<uuid>
  [CAM A] idx=0 abierta
  [REC] Grabando → <fight_id>_round1.mp4
  [EVENT] fighter=<uuid> speed=4.21 conf=0.53
"""

import argparse
import os
import sys
import threading
import time

import cv2
import numpy as np
import requests

# ══════════════════════════════════════════════════════════════════
#  GPU DETECTION — DirectML (AMD) → CUDA (NVIDIA) → CPU
# ══════════════════════════════════════════════════════════════════
_DEVICE  = "cpu"
_DML_DEV = None

try:
    import torch_directml
    _DML_DEV = torch_directml.device()
    _DEVICE  = "dml"
    print("[GPU] torch-directml → AMD GPU")
except ImportError:
    try:
        import torch
        print("CUDA:", torch.cuda.is_available())
        if torch.cuda.is_available():
            _DEVICE = "cuda"
            print(f"[GPU] CUDA: {torch.cuda.get_device_name(0)}")
        else:
            print("[GPU] Sin GPU acelerada — usando CPU")
    except ImportError:
        print("[GPU] torch no disponible — usando CPU")

# ══════════════════════════════════════════════════════════════════
#  CONSTANTES
# ══════════════════════════════════════════════════════════════════
_SUPABASE_URL   = "https://eeshomcqztvjkvycdfwi.supabase.co"
BASE_URL        = f"{_SUPABASE_URL}/functions/v1/ai-strike-ingest"
API_KEY         = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                   ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlc2hvbWNxenR2amt2eWNkZndpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNDUyMDAsImV4cCI6MjA3MTgyMTIwMH0"
                   ".JbOPpqzJvzojVRP3hV4QuDeetzRVpRxoaZeBAXrCb2c")
DEVICE_ID       = "vision_engine_01"

# Resolución 720p para V1 — más estable que 1080p en USB
CAM_W, CAM_H    = 1280, 720

# Umbrales de detección de golpes (ajustar según setup físico)
STRIKE_SPEED_MS = 3.5    # m/s velocidad de muñeca mínima
STRIKE_DIST_M   = 0.15   # m distancia máxima al oponente para contar impacto
STRIKE_COOL_S   = 0.50   # s cooldown mínimo entre golpes del mismo luchador
PIX_PER_M       = 200.0  # píxeles/metro para 720p a ~2m de distancia (calibrar)

# COCO keypoint indices usados
KP_NOSE     = 0
KP_L_WRIST  = 9
KP_R_WRIST  = 10


# ══════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════
def _headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "apikey":         API_KEY,
    }


# ══════════════════════════════════════════════════════════════════
#  FIGHTER ID API — consume la web, no inventa datos
# ══════════════════════════════════════════════════════════════════
class FighterIDAPI:
    """
    Contrato: la WEB es dueña de fight_id y fighters.
    El motor solo llama /start, recibe los IDs, y envía /event.
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url   = base_url
        self.session_id = None   # viene de /start
        self.fight_id   = None   # viene de /start
        self.red        = None   # UUID rojo — viene de /start
        self.blue       = None   # UUID azul — viene de /start

    def start_session(self, fight_id: str) -> None:
        """
        POST /start → obtiene session_id, fight_id y fighter UUIDs desde la web.
        Lanza RuntimeError si el backend no responde correctamente.
        """
        resp = requests.post(
            f"{self.base_url}/start",
            json={
                "fight_id":  fight_id,
                "device_id": DEVICE_ID,
                "cameras":   [0, 1, 2],
            },
            headers=_headers(),
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

    def send_event(self, fighter_id: str, confidence: float) -> None:
        """POST /event — no bloquea el loop principal (fire-and-forget en hilo)."""
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
            requests.post(
                f"{self.base_url}/event",
                json=payload,
                headers=_headers(),
                timeout=5,
            )
        except Exception as e:
            print(f"[EVENT] Error enviando: {e}")

    def resolve_fighter(self, track_id: str):
        """Mapea 'red'/'blue' → UUID de la DB. Los IDs vienen de la web."""
        return self.red if track_id == "red" else self.blue


# ══════════════════════════════════════════════════════════════════
#  CAMERA STREAM — captura continua sin bloquear el loop principal
# ══════════════════════════════════════════════════════════════════
class CameraStream:
    """Hilo de captura continua. read() devuelve el último frame sin bloquear."""

    def __init__(self, idx: int):
        self.idx  = idx
        self._cap = None
        self._frame: np.ndarray | None = None
        self._ts    = 0.0
        self._lock  = threading.Lock()
        self._running = False
        self._open()

    def _open(self) -> None:
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self.idx, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(3):
                cap.read()
            time.sleep(0.25)
            self._cap = cap
            bk = {cv2.CAP_DSHOW: "DSHOW", cv2.CAP_MSMF: "MSMF",
                  cv2.CAP_ANY: "ANY"}.get(backend, str(backend))
            print(f"[CAM {self.idx}] abierta  backend={bk}  "
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            return
        print(f"[CAM {self.idx}] ERROR — no se pudo abrir con ningún backend")

    def start(self) -> "CameraStream":
        self._running = True
        threading.Thread(target=self._update, daemon=True,
                         name=f"CamStream{self.idx}").start()
        return self

    def _update(self) -> None:
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.05)
                continue
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame
                    self._ts    = time.perf_counter()
            else:
                time.sleep(0.005)

    def read(self):
        """Returns (frame, timestamp) — frame may be None if not ready yet."""
        with self._lock:
            return self._frame, self._ts

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()


# ══════════════════════════════════════════════════════════════════
#  POSE DETECTOR — ONNX + DirectML con fallback a ultralytics
# ══════════════════════════════════════════════════════════════════
class PoseDetector:
    """
    Detección de pose YOLOv8-pose.
    Prioridad: onnxruntime-directml → ultralytics (con DirectML/CUDA).
    Si yolov8n-pose.onnx no existe, lo exporta automáticamente desde el .pt.
    """

    ONNX_PATH = "yolov8n-pose.onnx"
    PT_PATH   = "yolov8n-pose.pt"
    CONF_THR  = 0.45

    def __init__(self):
        self._ort_session = None
        self._yolo        = None
        self._input_name  = None
        self._init()

    def _init(self) -> None:
        # ── Intento 1: onnxruntime-directml ──────────────────────
        try:
            import onnxruntime as ort
            if not os.path.exists(self.ONNX_PATH):
                self._export_onnx()
            providers = (["DmlExecutionProvider"]
                         if _DEVICE in ("dml", "cuda")
                         else ["CPUExecutionProvider"])
            self._ort_session = ort.InferenceSession(
                self.ONNX_PATH, providers=providers
            )
            self._input_name = self._ort_session.get_inputs()[0].name
            print(f"[ONNX] Cargado — providers={providers}")
            return
        except ImportError:
            print("[ONNX] onnxruntime no instalado — "
                  "instala: pip install onnxruntime-directml")
        except Exception as e:
            print(f"[ONNX] Error al cargar: {e}")

        # ── Fallback: ultralytics ─────────────────────────────────
        self._init_ultralytics()

    def _export_onnx(self) -> None:
        print("[ONNX] Exportando yolov8n-pose.pt → yolov8n-pose.onnx…")
        from ultralytics import YOLO
        m = YOLO(self.PT_PATH)
        m.export(format="onnx", imgsz=640, opset=12, simplify=True)
        print("[ONNX] Exportación completa")

    def _init_ultralytics(self) -> None:
        from ultralytics import YOLO
        self._yolo = YOLO(self.PT_PATH)
        if _DEVICE == "dml" and _DML_DEV is not None:
            self._yolo.to(_DML_DEV)
        elif _DEVICE == "cuda":
            self._yolo.to("cuda")
        print(f"[YOLO] Modelo cargado — device={_DEVICE}")

    # ── Inferencia ────────────────────────────────────────────────

    def infer(self, frame: np.ndarray) -> list:
        """
        Returns list of person dicts:
          [{"keypoints": np.array(17,3), "bbox": [x1,y1,x2,y2], "conf": float}]
        Keypoints columnas: (x_pixels, y_pixels, confidence)
        Índices COCO: 0=nariz, 9=muñeca_izq, 10=muñeca_der
        """
        if self._ort_session is not None:
            return self._infer_onnx(frame)
        return self._infer_yolo(frame)

    def _infer_onnx(self, frame: np.ndarray) -> list:
        h_orig, w_orig = frame.shape[:2]
        img = cv2.resize(frame, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = np.transpose(img, (2, 0, 1))[np.newaxis]

        outputs = self._ort_session.run(None, {self._input_name: inp})
        return self._parse_onnx(outputs[0], w_orig, h_orig)

    def _parse_onnx(self, output: np.ndarray,
                    w_orig: int, h_orig: int) -> list:
        """
        YOLOv8-pose ONNX output: [1, 56, N]
        56 = 4 (cx,cy,w,h) + 1 (obj_conf) + 17×3 (kps)
        """
        sx, sy = w_orig / 640.0, h_orig / 640.0
        data   = output[0]                  # [56, N] or [N, 56]
        if data.ndim == 2 and data.shape[0] == 56:
            data = data.T                   # → [N, 56]

        persons = []
        for det in data:
            conf = float(det[4])
            if conf < self.CONF_THR:
                continue
            cx, cy, w, h = (det[0]*sx, det[1]*sy, det[2]*sx, det[3]*sy)
            x1, y1, x2, y2 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
            kps_raw  = det[5:].reshape(17, 3).copy()
            kps_raw[:, 0] *= sx
            kps_raw[:, 1] *= sy
            persons.append({
                "keypoints": kps_raw,
                "bbox":      [x1, y1, x2, y2],
                "conf":      conf,
            })
        return persons

    def _infer_yolo(self, frame: np.ndarray) -> list:
        results = self._yolo(frame, imgsz=640, conf=self.CONF_THR, verbose=False)
        persons = []
        r = results[0]
        if r.keypoints is None or r.keypoints.xy is None:
            return persons
        kps_xy   = r.keypoints.xy.cpu().numpy()
        kps_conf = (r.keypoints.conf.cpu().numpy()
                    if r.keypoints.conf is not None
                    else np.ones((len(kps_xy), 17)))
        boxes    = (r.boxes.xyxy.cpu().numpy()
                    if r.boxes is not None else [])
        for i in range(len(kps_xy)):
            kps = np.zeros((17, 3))
            kps[:, :2] = kps_xy[i]
            kps[:, 2]  = kps_conf[i]
            bbox = boxes[i].tolist() if i < len(boxes) else [0, 0, 0, 0]
            persons.append({"keypoints": kps, "bbox": bbox, "conf": 1.0})
        return persons


# ══════════════════════════════════════════════════════════════════
#  SIMPLE TRACKER — asignación por posición horizontal
# ══════════════════════════════════════════════════════════════════
class SimpleTracker:
    """
    Asigna esquinas a personas detectadas por posición horizontal.
    El luchador más a la izquierda = rojo, más a la derecha = azul.
    Funciona sin entrenamiento — suficiente para V1.
    """

    def assign(self, persons: list) -> dict:
        """Returns {"red": person, "blue": person} — subset si hay < 2 personas."""
        if not persons:
            return {}
        if len(persons) == 1:
            return {"red": persons[0]}
        # Ordenar por centro horizontal del bbox
        sorted_p = sorted(persons[:2],
                          key=lambda p: (p["bbox"][0] + p["bbox"][2]) / 2)
        return {"red": sorted_p[0], "blue": sorted_p[1]}


# ══════════════════════════════════════════════════════════════════
#  STRIKE DETECTOR — reglas biomecánicas
# ══════════════════════════════════════════════════════════════════
class StrikeDetector:
    """
    Detecta golpes usando velocidad de muñeca y distancia al oponente.
    No usa ML — reglas simples calibradas por umbrales físicos.
    """

    def __init__(self):
        self._prev: dict  = {}          # corner → (lw, rw, t)
        self._last: dict  = {}          # corner → último timestamp de golpe

    def detect(self, corner: str, person: dict,
               opponent: dict | None = None):
        """
        Returns (strike: bool, speed_ms: float, confidence: float)
        speed_ms: velocidad máxima de muñeca en m/s
        confidence: 0.0–1.0, escalada por velocidad
        """
        kps  = person["keypoints"]
        lw   = kps[KP_L_WRIST, :2].copy()
        rw   = kps[KP_R_WRIST, :2].copy()
        now  = time.time()

        # Cooldown — evita duplicados
        if now - self._last.get(corner, 0) < STRIKE_COOL_S:
            self._prev[corner] = (lw, rw, now)
            return False, 0.0, 0.0

        prev = self._prev.get(corner)
        self._prev[corner] = (lw, rw, now)

        if prev is None:
            return False, 0.0, 0.0

        prev_lw, prev_rw, prev_t = prev
        dt = now - prev_t
        if dt < 0.005:
            return False, 0.0, 0.0

        speed_l = float(np.linalg.norm(lw - prev_lw)) / dt / PIX_PER_M
        speed_r = float(np.linalg.norm(rw - prev_rw)) / dt / PIX_PER_M
        speed   = max(speed_l, speed_r)

        if speed < STRIKE_SPEED_MS:
            return False, speed, 0.0

        # Verificar distancia al oponente si disponible
        if opponent is not None:
            opp_nose   = opponent["keypoints"][KP_NOSE, :2]
            striker_w  = rw if speed_r >= speed_l else lw
            dist       = float(np.linalg.norm(striker_w - opp_nose)) / PIX_PER_M
            if dist > STRIKE_DIST_M:
                return False, speed, 0.0

        confidence = min(speed / 8.0, 1.0)
        self._last[corner] = now
        return True, speed, confidence


# ══════════════════════════════════════════════════════════════════
#  VIDEO RECORDER
# ══════════════════════════════════════════════════════════════════
class VideoRecorder:
    """Graba el stream de cámara principal en MP4."""

    def __init__(self, fight_id: str, round_num: int = 1,
                 fps: int = 30, size: tuple = (CAM_W, CAM_H)):
        # Nombre de archivo usa fight_id de la web — nunca uuid4 local
        self.filename = f"{fight_id}_round{round_num}.mp4"
        self._writer  = cv2.VideoWriter(
            self.filename,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            size,
        )
        print(f"[REC] Grabando → {self.filename}")

    def write(self, frame: np.ndarray) -> None:
        if frame is not None:
            self._writer.write(frame)

    def stop(self) -> None:
        self._writer.release()
        print(f"[REC] Guardado → {self.filename}")


# ══════════════════════════════════════════════════════════════════
#  VISION MOTOR V1 — clase principal
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
                 cam_a: int = 0, cam_b: int = 1, cam_c: int = 2):
        # Camera map explícito — logueado al arrancar para diagnóstico
        self.camera_map = {"A": cam_a, "B": cam_b, "C": cam_c}
        print(f"[CAM MAP] {self.camera_map}")

        self._fight_id = fight_id
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

        # Abrir streams para cada cámara en el map
        for role, idx in self.camera_map.items():
            if idx is not None:
                stream = CameraStream(idx).start()
                self._streams[role] = stream
                print(f"[CAM {role}] idx={idx} stream activo")

        if "A" not in self._streams or not self._streams["A"].is_open():
            raise RuntimeError("[MOTOR] Cámara A no disponible — abortando")

        # Video grabado con fight_id de la web
        self.recorder = VideoRecorder(self.api.fight_id, round_num=1)
        self._running = True

        print("[MOTOR] Bucle de detección iniciado — Ctrl+C para detener")
        self._loop()

    def _loop(self) -> None:
        fps_frames = 0
        fps_t0     = time.time()

        while self._running:
            frame, ts = self._streams["A"].read()
            if frame is None:
                time.sleep(0.01)
                continue

            # Detección de pose
            persons = self.detector.infer(frame)

            # Asignación de esquinas por posición horizontal
            roles = self.tracker.assign(persons)

            # Grabar frame
            self.recorder.write(frame)

            # Detección de golpes para cada esquina
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

            # FPS contador cada 5 segundos
            fps_frames += 1
            if time.time() - fps_t0 >= 5.0:
                fps = fps_frames / (time.time() - fps_t0)
                print(f"[FPS] {fps:.1f}  personas={len(persons)}")
                fps_frames = 0
                fps_t0     = time.time()

    def stop(self) -> None:
        self._running = False
        if self.recorder:
            self.recorder.stop()
        for role, stream in self._streams.items():
            stream.stop()
            print(f"[CAM {role}] cerrada")
        print("[MOTOR] Detenido")


# ══════════════════════════════════════════════════════════════════
#  ENTRYPOINT
# ══════════════════════════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(
        description="FighterID Vision Motor V1 — headless, sin GUI"
    )
    parser.add_argument(
        "--fight-id",
        default=None,
        help="Fight ID creado por la web (fighter-id.org). "
             "También puede pasarse via env var FIGHT_ID.",
    )
    parser.add_argument("--cam-a", type=int, default=0,
                        help="Índice OpenCV cámara A (principal, IA+Kalman)")
    parser.add_argument("--cam-b", type=int, default=1,
                        help="Índice OpenCV cámara B (profundidad/estéreo)")
    parser.add_argument("--cam-c", type=int, default=2,
                        help="Índice OpenCV cámara C (cenital overhead)")
    args = parser.parse_args()

    fight_id = args.fight_id or os.environ.get("FIGHT_ID")

    if not fight_id:
        print("[ERROR] Se requiere fight_id para arrancar el motor.")
        print("        La web crea el fight_id — el motor NUNCA lo inventa.")
        print()
        print("  Opción A: python vision_motor_v1.py --fight-id <id>")
        print("  Opción B: FIGHT_ID=<id> python vision_motor_v1.py")
        sys.exit(1)

    motor = VisionMotorV1(
        fight_id=fight_id,
        cam_a=args.cam_a,
        cam_b=args.cam_b,
        cam_c=args.cam_c,
    )

    try:
        motor.start()
    except KeyboardInterrupt:
        print("\n[MOTOR] Interrumpido por usuario")
    except RuntimeError as e:
        print(f"\n[MOTOR] Error: {e}")
        sys.exit(1)
    finally:
        motor.stop()


if __name__ == "__main__":
    main()
