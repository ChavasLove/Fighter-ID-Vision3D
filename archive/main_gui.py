"""
FighterID Vision v4.1  –  3-Camera · GPU AMD · Hardened Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v3.6 → v4.0  Upgrade changelog:
  [1] Independent YOLO inference threads per camera (A, B, C)
  [2] Hungarian algorithm multi-camera matching (scipy)
  [3] Kalman filter per keypoint (17 kp/person) — eliminates jitter
  [4] OpenCV stereo calibration module (checkerboard)
  [5] Biomechanical punch classifier (shoulder/hip rotation, elbow angle, BODYSHOT)
  [6] FighterID Platform API export (POST /ai-strike-ingest/event)
  [7] Dataset capture system (frames + keypoints + metadata)
  [8] System telemetry panel (FPS, GPU load, inference latency, triangulation)

pip install customtkinter pillow ultralytics opencv-python numpy torch-directml scipy requests
"""
import os, subprocess, json, requests, csv, pathlib, uuid
os.environ["OPENCV_LOG_LEVEL"]     = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
import cv2, numpy as np, time, math, datetime, threading
from collections import deque
from ultralytics import YOLO
import customtkinter as ctk
from PIL import Image
try:
    from scipy.optimize import linear_sum_assignment
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    print("[WARN] scipy not found — falling back to greedy matching. pip install scipy")

# ── GPU: DirectML (AMD/Intel) → CUDA → CPU ──────────────────────
_DEVICE = "cpu"
try:
    import torch_directml
    _DML_DEV = torch_directml.device()
    _DEVICE  = "dml"
    print("[GPU] torch-directml → AMD GPU")
except ImportError:
    try:
        import torch
        if torch.cuda.is_available():
            _DEVICE = "cuda"
            print(f"[GPU] CUDA: {torch.cuda.get_device_name(0)}"
                  f"  VRAM={torch.cuda.get_device_properties(0).total_memory//1024**2}MB"
                  f"  CUDAv{torch.version.cuda}")
        else:
            # Diagnóstico detallado — ayuda al usuario a saber qué instalar
            _cuda_built = getattr(torch.version, 'cuda', None)
            print("[CPU] sin GPU acelerada")
            if _cuda_built is None:
                print("      ⚠ PyTorch instalado SIN soporte CUDA (versión CPU-only)")
                print("      → Reinstala con CUDA para activar la GPU NVIDIA:")
                print("        pip uninstall torch torchvision torchaudio -y")
                print("        pip install torch torchvision torchaudio "
                      "--index-url https://download.pytorch.org/whl/cu121")
            else:
                import ctypes, sys
                _nv = None
                try:
                    _nv = ctypes.windll.nvcuda.cuInit
                    print(f"      PyTorch compilado para CUDA {_cuda_built} "
                          f"pero el driver NVIDIA no responde correctamente")
                    print(f"      → Actualiza el driver NVIDIA desde: "
                          f"https://www.nvidia.com/Download/index.aspx")
                except Exception:
                    print(f"      PyTorch compilado para CUDA {_cuda_built} "
                          f"pero no detecta GPU NVIDIA instalada")
                    print(f"      → Verifica que los drivers NVIDIA estén instalados")
    except ImportError:
        print("[CPU] torch no disponible — instala: pip install torch")
try:
    import torch
    torch.set_num_threads(4)
    print("CUDA:", torch.cuda.is_available())
except ImportError:
    pass
cv2.setNumThreads(4)
cv2.ocl.setUseOpenCL(False)

# ══════════════════════════════════════════════════════════════════
#  VERSION  —  actualizar en cada push significativo
# ══════════════════════════════════════════════════════════════════
BUILD_VERSION = "v4.3"
BUILD_DATE    = "2026-03-15"          # YYYY-MM-DD del último push

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
ROUND_TIME       = 180;  REST_TIME        = 60;   TOTAL_ROUNDS     = 3
INFER_IMGSZ      = 512;  INFER_EVERY      = 3;    INFER_CONF       = 0.28
# Per-camera inference rates (matched to physical FPS)
INFER_EVERY_AB   = 2     # CAM A & B — 60fps laterales → YOLO a ~30fps
INFER_EVERY_C    = 1     # CAM C — 30fps cenital → YOLO cada frame
# Overhead camera calibration & hook detection
CAM_C_PX_PER_M   = 400.0 # Píxeles por metro en vista cenital (ajustar según altura de montaje)
CAM_C_TS_BUF     = 8     # Frames en el buffer de timestamp para sincronización 60↔30fps
HOOK_ARC_THR_DEG = 18.0  # Curvatura mínima (°) en plano XZ para confirmar HOOK (18° = +38% más sensible)
VOTE_WINDOW      = 45;   VOTE_NEEDED      = 18
PUNCH_SPD_THR_MS = 0.40; PUNCH_SPD_CAP_MS = 25.0   # 0.55→0.40: captura golpes más lentos/cortos
EXTENSION_THR_M  = 0.10; RETRACTION_RATIO = 0.72   # 0.14→0.10m: jabs cortos; 0.58→0.72: menos retracción
MIN_PUNCH_DUR    = 0.03; MAX_PUNCH_DUR    = 0.85   # 0.05→0.03s: golpes rápidos; 0.70→0.85s: más margen
HIT_R_M          = 0.30; HEAD_HIT_R_M     = 0.20
BODY_HIT_R_M     = 0.35
DODGE_SPD_MS     = 0.40; HISTORY_LEN      = 20
CAM_W, CAM_H     = 1920, 1080
FOCAL_EST        = CAM_W * 0.8
CX, CY           = CAM_W / 2, CAM_H / 2
MAX_CAMS         = 6          # Reduced from 10 – typical desktop never exceeds 6 USB cams
MAX_FOUND_CAMS   = 3          # Stop scan early once 3 cameras discovered
DEFAULT_BASELINE = 1.50

# ── Professional boxing biomechanical thresholds ────────────────
# Research refs: McGill 2010, Loturco 2014, Filimonov 1985
POWER_PUNCH_SPD_MS   = 2.0    # Wrist velocity threshold for "power punch" in scoring
SCORING_PUNCH_SPD_MS = 0.70   # 1.0→0.70 m/s: cuenta más golpes como "limpios" en modo TEST
COMBO_WINDOW_S       = 1.8    # Max gap (s) between punches to count as a combination
STANCE_THRESH_M      = 0.04   # Shoulder X-diff threshold for stance detection

# Professional boxing punch type groups
POWER_PUNCH_TYPES  = {"CROSS", "HOOK", "UPPERCUT", "OVERHAND"}
SCORING_PUNCH_TYPES = {"JAB", "CROSS", "HOOK", "UPPERCUT", "OVERHAND", "BODYSHOT"}

# FighterID Platform API — credenciales desde .env (nunca hardcodeadas)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
if not SUPABASE_URL:
    print("[CONFIG] ⚠  SUPABASE_URL no definida — crea .env desde .env.example")
if not SUPABASE_ANON_KEY:
    print("[CONFIG] ⚠  SUPABASE_ANON_KEY no definida — crea .env desde .env.example")
FIGHTERID_EDGE_URL = os.getenv("FIGHTERID_EDGE_URL", f"{SUPABASE_URL}/functions/v1")
FIGHTERID_API_URL  = os.getenv("FIGHTERID_API_URL",  f"{SUPABASE_URL}/functions/v1/ai-strike-ingest")
FIGHTERID_API_KEY  = os.getenv("FIGHTERID_API_KEY",  SUPABASE_ANON_KEY)
API_ENABLED        = os.getenv("API_ENABLED", "true").strip().lower() == "true"
MODEL_VERSION      = BUILD_VERSION

# Dataset capture
DATASET_DIR = pathlib.Path("dataset_capture")
DATASET_ENABLED = False

# ── Live Stream — Supabase + RTMP ──────────────────────────────────────────────
# Configurar via botón ⚙ EN VIVO en la barra lateral o editando fighterid_stream.json
# SUPABASE_URL / SUPABASE_ANON_KEY ya cargados desde .env arriba
SUPABASE_TABLE_LIVE   = "live_session"
SUPABASE_TABLE_ROUNDS = "round_results"
STREAM_RTMP_URL       = ""   # rtmp://... (YouTube/Twitch/Mux/custom — opcional)
STREAM_FPS_TARGET     = 30
LIVE_STREAM_ENABLED   = False
_STREAM_CFG_FILE      = pathlib.Path("fighterid_stream.json")

# OpenCV BGR
BLK=(8,8,12);    WHT=(255,255,255); GRY=(120,120,120)
RED=(30,30,220); BLU=(255,180,20);  CYN=(230,230,20)
GRN=(60,230,60); ORG=(0,165,255);   MAG=(220,30,220); YLW=(0,210,230)
FD=cv2.FONT_HERSHEY_DUPLEX; FS=cv2.FONT_HERSHEY_SIMPLEX

# HSV gloves
R_LO1=np.array([0,120,70],np.uint8);   R_HI1=np.array([10,255,255],np.uint8)
R_LO2=np.array([165,120,70],np.uint8); R_HI2=np.array([180,255,255],np.uint8)
B_LO =np.array([90,100,50],np.uint8);  B_HI =np.array([140,255,255],np.uint8)
W_S_MAX=55; W_V_MIN=160
SK1_LO=np.array([0,20,60],np.uint8);   SK1_HI=np.array([25,210,255],np.uint8)
SK2_LO=np.array([0,10,40],np.uint8);   SK2_HI=np.array([20,130,210],np.uint8)
# Black shirt: dark pixels — V < 60, covers >30% of torso ROI
BK_V_MAX = 60; BK_RATIO_MIN = 0.30

# GUI hex — sober, minimalist dark palette
GUI_BG      = "#0a0a0f"; GUI_PANEL   = "#10101a"; GUI_CARD    = "#171720"
GUI_BORDER  = "#222232"; GUI_RED     = "#c42830"; GUI_BLUE    = "#1a6ee0"
GUI_CYAN    = "#00a8b8"; GUI_GREEN   = "#259645"; GUI_YELLOW  = "#b89010"
GUI_MAGENTA = "#904090"; GUI_WHITE   = "#d0d0e0"; GUI_GRAY    = "#484858"
GUI_ORANGE  = "#c86800"; GUI_BLACK   = "#060608"

CALIB_FILE = "stereo_calib.json"

# ══════════════════════════════════════════════════════════════════
#  [3] KALMAN FILTER PER KEYPOINT
# ══════════════════════════════════════════════════════════════════
class KalmanKeypoints:
    """
    One Kalman filter per keypoint (17 kp). State = [x, y, vx, vy].
    Eliminates jitter and gives smooth velocity estimates.
    """
    def __init__(self, n_kp=17, process_noise=1e-2, meas_noise=1e-1):
        self.n_kp = n_kp
        self.filters = []
        for _ in range(n_kp):
            kf = cv2.KalmanFilter(4, 2)
            kf.transitionMatrix    = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]], np.float32)
            kf.measurementMatrix   = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
            kf.processNoiseCov     = np.eye(4, dtype=np.float32) * process_noise
            kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * meas_noise
            kf.errorCovPost        = np.eye(4, dtype=np.float32)
            kf.statePost           = np.zeros((4,1), dtype=np.float32)
            self.filters.append(kf)
        self._initialized = [False] * n_kp

    def update(self, kp_xy: np.ndarray) -> np.ndarray:
        """
        kp_xy: (17, 2) array of (x, y). Returns smoothed (17, 2).
        Keypoints with (0,0) are treated as invisible — only predicted.
        """
        out = np.zeros_like(kp_xy)
        for i, kf in enumerate(self.filters):
            x, y = float(kp_xy[i][0]), float(kp_xy[i][1])
            visible = not (x == 0.0 and y == 0.0)
            if visible and not self._initialized[i]:
                kf.statePost[:2] = np.array([[x],[y]], dtype=np.float32)
                self._initialized[i] = True
            pred = kf.predict()
            if visible:
                meas = np.array([[x],[y]], dtype=np.float32)
                corrected = kf.correct(meas)
                out[i] = corrected[:2].ravel()
            else:
                out[i] = pred[:2].ravel()
        return out

    def reset(self):
        self._initialized = [False] * self.n_kp
        for kf in self.filters:
            kf.statePost = np.zeros((4,1), dtype=np.float32)
            kf.errorCovPost = np.eye(4, dtype=np.float32)

# ══════════════════════════════════════════════════════════════════
#  [3] POSE TRACKER (with Kalman)
# ══════════════════════════════════════════════════════════════════
class PoseTracker:
    def __init__(self):
        self._prev_gray: np.ndarray = None
        self._tracked_kp: list     = []
        self._tracked_cf: list     = []
        self._kalman_map: dict     = {}   # pid -> KalmanKeypoints
        self._drift_frames: int    = 0
        self._lk_params = dict(
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
        )

    def _get_kalman(self, idx: int) -> KalmanKeypoints:
        if idx not in self._kalman_map:
            self._kalman_map[idx] = KalmanKeypoints()
        return self._kalman_map[idx]

    def update_from_yolo(self, frame_gray: np.ndarray, kp_list, cf_list):
        if not kp_list: return
        self._prev_gray  = frame_gray.copy()
        # Apply Kalman smoothing on fresh YOLO detections
        smoothed = []
        for idx, kp in enumerate(kp_list):
            kal = self._get_kalman(idx)
            sk  = kal.update(kp.astype(np.float32))
            smoothed.append(sk)
        self._tracked_kp = smoothed
        self._tracked_cf = [c.copy() for c in cf_list]
        self._drift_frames = 0

    def track(self, frame_gray: np.ndarray):
        if self._prev_gray is None or not self._tracked_kp:
            return self._tracked_kp, self._tracked_cf
        self._drift_frames += 1
        if self._drift_frames > INFER_EVERY * 3:
            return self._tracked_kp, self._tracked_cf
        new_kp_list = []
        for idx, (kp, cf) in enumerate(zip(self._tracked_kp, self._tracked_cf)):
            pts  = kp.astype(np.float32)
            mask = (pts[:, 0] > 0) | (pts[:, 1] > 0)
            if mask.sum() < 3:
                new_kp_list.append(kp); continue
            pts_in = pts[mask].reshape(-1, 1, 2)
            try:
                pts_out, st, _ = cv2.calcOpticalFlowPyrLK(
                    self._prev_gray, frame_gray, pts_in, None, **self._lk_params)
                if pts_out is None or st is None:
                    new_kp_list.append(kp); continue
                new_pts = kp.copy()
                good = st.ravel() == 1
                for j, (gi, ok) in enumerate(zip(np.where(mask)[0], good)):
                    if ok and j < len(pts_out):
                        x, y = pts_out[j].ravel()
                        if math.isfinite(x) and math.isfinite(y) and 0<=x<CAM_W and 0<=y<CAM_H:
                            new_pts[gi] = [x, y]
                # Apply Kalman on tracked result
                kal = self._get_kalman(idx)
                new_pts = kal.update(new_pts)
                new_kp_list.append(new_pts)
            except Exception as e:
                print(f"[PoseTracker] optical flow error: {e}")
                new_kp_list.append(kp)
        self._tracked_kp = new_kp_list
        self._prev_gray  = frame_gray.copy()
        return new_kp_list, self._tracked_cf

# ══════════════════════════════════════════════════════════════════
#  CAMERA SCAN
# ══════════════════════════════════════════════════════════════════
def _get_device_names():
    try:
        ps = ("Get-PnpDevice -Class Camera -Status OK "
              "| Sort-Object InstanceId "
              "| Select-Object -ExpandProperty FriendlyName "
              "| ConvertTo-Json")
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            timeout=3, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore").strip()
        if out:
            data = json.loads(out)
            return [data] if isinstance(data, str) else list(data)
    except: pass
    return []

def _probe_camera(idx):
    """
    Detecta si existe una cámara en el índice dado.
    NO fuerza resolución — solo verifica accesibilidad y lee a resolución nativa.
    Forzar 1920x1080 durante el scan causa conflictos USB con cámaras del mismo
    modelo (reinicialización del driver en secuencia rápida → frames vacíos).
    La resolución se configura al abrir la cámara en el engine (open_cap).
    """
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):   # DSHOW first: stable indices on Win
        cap = None
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened(): cap.release(); continue
            # Dos lecturas de calentamiento sin cambiar nada
            cap.read(); time.sleep(0.08); cap.read()
            ok, frame = cap.read()
            if not ok or frame is None: cap.release(); continue
            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0 or fps > 240:
                t0 = time.time()
                for _ in range(6): cap.read()
                fps = round(6 / max(time.time() - t0, 0.001), 1)
            cap.release()
            return {'w': w, 'h': h, 'fps': fps}
        except Exception as e:
            print(f"  [probe] idx={idx} backend={backend}: {e}")
            if cap:
                try: cap.release()
                except: pass
    return None

def _res_score(c):
    w, h = c['w'], c['h']
    if w == 1920 and h == 1080: return (3, w*h)
    if w >= 1280 and h >= 720:  return (2, w*h)
    if w >= 640  and h >= 480:  return (1, w*h)
    return (0, w*h)

def scan_all_cameras():
    dev_names = _get_device_names()
    print(f"\n[{BUILD_VERSION} {BUILD_DATE}] Escaneando cámaras 0..{MAX_CAMS-1}…")
    candidates = []
    for i in range(MAX_CAMS):
        info = _probe_camera(i)
        if info is None:
            time.sleep(0.04)  # brief settle on miss
            # Early exit: all needed cameras already found + 1 miss
            if len(candidates) >= MAX_FOUND_CAMS:
                print(f"  → {MAX_FOUND_CAMS} cámaras encontradas, índice {i} vacío — scan completo")
                break
            continue
        time.sleep(0.10)  # USB driver settle after successful open (was 0.25s)
        name = dev_names[i] if i < len(dev_names) else f"Camara {i}"
        info.update({'index': i, 'name': name}); candidates.append(info)
        print(f"  [PROBE] [{i}] {name}  {info['w']}x{info['h']}@{info['fps']:.0f}fps")
        if len(candidates) >= MAX_FOUND_CAMS:
            print(f"  → Máximo de cámaras ({MAX_FOUND_CAMS}) alcanzado — finalizando scan")
            break
    # Cada índice OpenCV = 1 dispositivo físico independiente.
    # No se agrupa por nombre para no descartar cámaras del mismo modelo
    # (p.ej. dos Razer Kiyo X) — se añade sufijo #2, #3 cuando se repite.
    name_count: dict = {}; found = []
    for c in sorted(candidates, key=lambda x: x['index']):
        base = c['name']; name_count[base] = name_count.get(base, 0) + 1
        display = base if name_count[base] == 1 else f"{base} #{name_count[base]}"
        c['name'] = display
        label = f"[{c['index']}] {display}  {c['w']}x{c['h']}@{c['fps']:.0f}fps"
        c['label'] = label; found.append(c)
        print(f"  [OK]    {label}")
    print(f"  → {len(found)} dispositivo(s) físico(s) detectado(s)\n")
    return found

ALL_CAMERAS = []

# ══════════════════════════════════════════════════════════════════
#  [4] STEREO CALIBRATION MODULE
# ══════════════════════════════════════════════════════════════════
class StereoCalibrator:
    """
    Captures checkerboard images from CAM A + CAM B, runs cv2.stereoCalibrate,
    and saves camera matrices + distortion + R + T to JSON.
    """
    def __init__(self, board_w=9, board_h=6, square_mm=25.0):
        self.board_size = (board_w, board_h)
        self.square_m   = square_mm / 1000.0
        self.obj_pts: list = []
        self.img_pts_a: list = []
        self.img_pts_b: list = []
        self._objp = np.zeros((board_w * board_h, 3), np.float32)
        self._objp[:, :2] = np.mgrid[0:board_w, 0:board_h].T.reshape(-1, 2) * self.square_m
        self.n_captures  = 0
        self.K_a = self.d_a = self.K_b = self.d_b = None
        self.R   = self.T   = None
        self.loaded = False

    def try_find(self, frame_a, frame_b):
        """Returns (corners_a, corners_b) or (None, None)."""
        g_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
        g_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
        ok_a, c_a = cv2.findChessboardCorners(g_a, self.board_size, flags)
        ok_b, c_b = cv2.findChessboardCorners(g_b, self.board_size, flags)
        if ok_a and ok_b:
            crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.001)
            c_a = cv2.cornerSubPix(g_a, c_a, (11,11), (-1,-1), crit)
            c_b = cv2.cornerSubPix(g_b, c_b, (11,11), (-1,-1), crit)
            return c_a, c_b
        return None, None

    def capture(self, frame_a, frame_b):
        """Attempt to find and store a calibration pair. Returns True on success."""
        c_a, c_b = self.try_find(frame_a, frame_b)
        if c_a is not None:
            self.obj_pts.append(self._objp.copy())
            self.img_pts_a.append(c_a)
            self.img_pts_b.append(c_b)
            self.n_captures += 1
            return True
        return False

    def calibrate(self, img_size):
        """Run stereoCalibrate. Returns (baseline_m, focal_px) or raises."""
        if self.n_captures < 10:
            raise RuntimeError(f"Need ≥10 captures, have {self.n_captures}")
        flags = (cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_ZERO_TANGENT_DIST |
                 cv2.CALIB_SAME_FOCAL_LENGTH | cv2.CALIB_RATIONAL_MODEL |
                 cv2.CALIB_FIX_K3 | cv2.CALIB_FIX_K4 | cv2.CALIB_FIX_K5)
        rms, K_a, d_a, K_b, d_b, R, T, E, F = cv2.stereoCalibrate(
            self.obj_pts, self.img_pts_a, self.img_pts_b,
            None, None, None, None, img_size,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-7),
            flags=flags)
        self.K_a, self.d_a = K_a, d_a
        self.K_b, self.d_b = K_b, d_b
        self.R, self.T = R, T
        self.loaded = True
        baseline_m = float(np.linalg.norm(T))
        focal_px   = float(K_a[0, 0])
        cx_px, cy_px = float(K_a[0, 2]), float(K_a[1, 2])
        self._save(rms, baseline_m, focal_px, cx_px, cy_px)
        return baseline_m, focal_px, cx_px, cy_px, rms

    def _save(self, rms, bl, f, cx, cy):
        data = {'rms': rms, 'baseline_m': bl, 'focal_px': f, 'cx': cx, 'cy': cy,
                'K_a': self.K_a.tolist(), 'd_a': self.d_a.tolist(),
                'K_b': self.K_b.tolist(), 'd_b': self.d_b.tolist(),
                'R': self.R.tolist(), 'T': self.T.tolist()}
        with open(CALIB_FILE, 'w') as fp: json.dump(data, fp, indent=2)
        print(f"[CALIB] Saved → {CALIB_FILE}  RMS={rms:.4f}")

    @staticmethod
    def load():
        if not os.path.exists(CALIB_FILE): return None
        try:
            with open(CALIB_FILE) as fp: d = json.load(fp)
            print(f"[CALIB] Loaded {CALIB_FILE}  baseline={d['baseline_m']:.3f}m")
            return d
        except Exception as e:
            print(f"[CALIB] Load error: {e}"); return None

# ══════════════════════════════════════════════════════════════════
#  STEREO FUSER
# ══════════════════════════════════════════════════════════════════
class StereoFuser:
    def __init__(self, baseline_m=DEFAULT_BASELINE, focal_px=FOCAL_EST, cx=CX, cy=CY):
        self.B = max(0.05, baseline_m); self.f = focal_px; self.cx = cx; self.cy = cy

    def triangulate(self, u_a, v_a, u_b, v_b):
        d = float(u_a) - float(u_b)
        if abs(d) < 1.0: return None
        Z = self.f * self.B / d
        if not math.isfinite(Z) or Z < 0.1 or Z > 20.0: return None
        X = Z * (float(u_a) - self.cx) / self.f
        Y = Z * (float(v_a) - self.cy) / self.f
        if not (math.isfinite(X) and math.isfinite(Y)): return None
        return (X, Y, Z)

    def depth_from_single(self, u, v, z=2.0):
        return (z*(float(u)-self.cx)/self.f, z*(float(v)-self.cy)/self.f, z)

    def fuse_keypoints(self, kp_a, kp_b, cf_a=None, cf_b=None):
        n = 17; fused = np.zeros((n, 2), np.float32); pts3d = {}; origin = {}
        for i in range(n):
            av = (i<len(kp_a) and not(kp_a[i][0]==0 and kp_a[i][1]==0)
                  and 0<kp_a[i][0]<CAM_W and 0<kp_a[i][1]<CAM_H)
            bv = (i<len(kp_b) and not(kp_b[i][0]==0 and kp_b[i][1]==0)
                  and 0<kp_b[i][0]<CAM_W and 0<kp_b[i][1]<CAM_H)
            ca = float(cf_a[i]) if (cf_a is not None and i<len(cf_a)) else 0.5
            cb = float(cf_b[i]) if (cf_b is not None and i<len(cf_b)) else 0.5
            if av and bv:
                p3 = self.triangulate(kp_a[i][0], kp_a[i][1], kp_b[i][0], kp_b[i][1])
                if p3: pts3d[i]=p3; origin[i]='AB'; fused[i]=kp_a[i][:2]
                else:
                    fused[i]=kp_a[i][:2] if ca>=cb else kp_b[i][:2]
                    pts3d[i]=self.depth_from_single(*fused[i]); origin[i]='A' if ca>=cb else 'B'
            elif av: fused[i]=kp_a[i][:2]; pts3d[i]=self.depth_from_single(*fused[i]); origin[i]='A'
            elif bv: fused[i]=kp_b[i][:2]; pts3d[i]=self.depth_from_single(*fused[i]); origin[i]='B'
        return fused, pts3d, origin

# ══════════════════════════════════════════════════════════════════
#  [1] INDEPENDENT INFER THREADS (A, B, C)
# ══════════════════════════════════════════════════════════════════
class InferThread(threading.Thread):
    def __init__(self, model, name="Infer"):
        super().__init__(daemon=True, name=name)
        self.model = model
        self._fin = None; self._rout = None
        self._lk = threading.Lock(); self._ev = threading.Event(); self._go = True
        self.last_latency_ms = 0.0
        self.total_infers    = 0

    def submit(self, frame):
        with self._lk: self._fin = frame.copy()
        self._ev.set()

    def result(self):
        with self._lk:
            r = self._rout; self._rout = None; return r

    def stop(self): self._go = False; self._ev.set()

    def run(self):
        _cpu_fallback = False
        while self._go:
            self._ev.wait(); self._ev.clear()
            if not self._go: break
            with self._lk: f = self._fin
            if f is None: continue
            t0 = time.perf_counter()
            try:
                r = self.model(f, imgsz=INFER_IMGSZ, conf=INFER_CONF, verbose=False)
                if _cpu_fallback:
                    print(f"[{self.name}] GPU recovered"); _cpu_fallback = False
                with self._lk: self._rout = r
            except Exception as e_gpu:
                if not _cpu_fallback:
                    print(f"[{self.name}] GPU failed ({e_gpu}), falling back to CPU")
                    _cpu_fallback = True
                try:
                    # Use explicit CPU fallback — do NOT pass device="cpu" when DML is active
                    # (it causes a second error); let YOLO use its current device binding
                    r = self.model(f, imgsz=INFER_IMGSZ, conf=INFER_CONF, verbose=False)
                    with self._lk: self._rout = r
                except Exception as e2:
                    print(f"[{self.name}] inference failed: {e2}")
            self.last_latency_ms = (time.perf_counter() - t0) * 1000
            self.total_infers += 1

# ══════════════════════════════════════════════════════════════════
#  CAMERA READER THREAD
# ══════════════════════════════════════════════════════════════════
class CamReader(threading.Thread):
    """Lee frames de una cámara continuamente en background.
    El main loop obtiene el último frame disponible sin bloquearse."""
    def __init__(self, cap):
        super().__init__(daemon=True, name="CamReader")
        self._cap   = cap
        self._frame = None
        self._lk    = threading.Lock()
        self._go    = True

    def read(self):
        with self._lk:
            f = self._frame
        return (f is not None, f)

    def stop(self):
        self._go = False

    def run(self):
        while self._go:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lk:
                    self._frame = frame
            else:
                time.sleep(0.005)

# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def glow(img, c, r, col, n=3):
    for i in range(n, 0, -1): cv2.circle(img, c, r+i*3, col, 1)
    cv2.circle(img, c, r, col, 2)

def classify_glove(frame, x, y, r=None):
    if r is None: r = max(10, int(10 * CAM_W / 640))
    h, w = frame.shape[:2]
    roi = frame[max(0,y-r):min(h,y+r), max(0,x-r):min(w,x+r)]
    if roi.size == 0: return {'white': False, 'red': False, 'blue': False}
    small = cv2.resize(roi, (48,48), interpolation=cv2.INTER_LINEAR)
    hsv = cv2.cvtColor(cv2.GaussianBlur(small,(5,5),0), cv2.COLOR_BGR2HSV)
    s, v = hsv[:,:,1], hsv[:,:,2]; mn = max(18, int(48*48*0.07))
    wm = (s<W_S_MAX)&(v>W_V_MIN); white = int(np.sum(wm)) > mn
    rm = cv2.bitwise_or(cv2.inRange(hsv,R_LO1,R_HI1), cv2.inRange(hsv,R_LO2,R_HI2))
    rm[wm] = 0; red = int(np.sum(rm>0)) > mn
    bm = cv2.inRange(hsv, B_LO, B_HI); bm[wm] = 0; blue = int(np.sum(bm>0)) > mn
    return {'white': white, 'red': red, 'blue': blue}

def detect_bare_hand(frame, x, y, r=None):
    """
    Returns True if the hand area looks like bare skin (no glove).
    Used to gate fight-mode start — both fighters must have gloves.
    """
    if r is None: r = max(10, int(10 * CAM_W / 640))
    h, w = frame.shape[:2]
    roi = frame[max(0,y-r):min(h,y+r), max(0,x-r):min(w,x+r)]
    if roi.size == 0: return False
    small = cv2.resize(roi, (48, 48), interpolation=cv2.INTER_LINEAR)
    hsv   = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2HSV)
    mn    = max(15, int(48 * 48 * 0.08))
    sm1   = cv2.inRange(hsv, SK1_LO, SK1_HI)
    sm2   = cv2.inRange(hsv, SK2_LO, SK2_HI)
    return int(np.sum(cv2.bitwise_or(sm1, sm2) > 0)) > mn

def bare_torso(frame, kp):
    if len(kp) < 13: return False
    try:
        pts = [kp[i] for i in [5,6,11,12] if kp[i][0]>0 and kp[i][1]>0]
        if len(pts) < 3: return False
        xs=[int(p[0]) for p in pts]; ys=[int(p[1]) for p in pts]
        H, W = frame.shape[:2]
        roi = frame[max(0,min(ys)):min(H,max(ys)+20), max(0,min(xs)-10):min(W,max(xs)+10)]
        if roi.size==0 or roi.shape[0]<12 or roi.shape[1]<12: return False
        sm  = cv2.resize(roi, (64,64), interpolation=cv2.INTER_LINEAR)
        hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
        sk  = cv2.bitwise_or(cv2.inRange(hsv,SK1_LO,SK1_HI), cv2.inRange(hsv,SK2_LO,SK2_HI))
        return float(np.sum(sk>0))/(64*64) > 0.15
    except: return False

def detect_black_shirt(frame, kp):
    """Returns True if the torso area is predominantly dark/black (black shirt)."""
    if len(kp) < 13: return False
    try:
        pts = [kp[i] for i in [5,6,11,12] if kp[i][0]>0 and kp[i][1]>0]
        if len(pts) < 3: return False
        xs=[int(p[0]) for p in pts]; ys=[int(p[1]) for p in pts]
        H, W = frame.shape[:2]
        roi = frame[max(0,min(ys)):min(H,max(ys)+20), max(0,min(xs)-10):min(W,max(xs)+10)]
        if roi.size==0 or roi.shape[0]<12 or roi.shape[1]<12: return False
        sm  = cv2.resize(roi, (64,64), interpolation=cv2.INTER_LINEAR)
        hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
        dark = (hsv[:,:,2] < BK_V_MAX)  # Very dark/black pixels
        return float(np.sum(dark)) / (64*64) > BK_RATIO_MIN
    except: return False

def extract_overhead_biomechanics(kp_top, px_per_m=None):
    """
    Extrae biomecánica desde la cámara cenital (vista superior).

    En vista cenital:
      eje U (horizontal imagen) ≈ eje X del mundo
      eje V (vertical imagen)   ≈ eje Z del mundo  (profundidad del ring)

    Retorna dict con:
      shoulder_angle_rad  — ángulo real del eje de hombros en plano XZ
      hip_angle_rad       — ángulo real del eje de caderas en plano XZ
      torso_rotation_deg  — separación angular hombro-cadera (cadena cinética real)
      base_width_m        — ancho de base (tobillos) en metros
      valid               — True si hay suficientes keypoints
    """
    if px_per_m is None: px_per_m = CAM_C_PX_PER_M
    result = {'shoulder_angle_rad': 0.0, 'hip_angle_rad': 0.0,
              'torso_rotation_deg': 0.0,  'base_width_m': 0.0, 'valid': False}
    if kp_top is None or len(kp_top) < 17: return result
    try:
        ls = kp_top[5];  rs = kp_top[6]   # hombros
        lh = kp_top[11]; rh = kp_top[12]  # caderas
        la = kp_top[15]; ra = kp_top[16]  # tobillos
        sh_ok  = ls[0]>0 and rs[0]>0
        hip_ok = lh[0]>0 and rh[0]>0
        if not (sh_ok or hip_ok): return result

        if sh_ok:
            theta_sh = math.atan2(float(rs[1]) - float(ls[1]),
                                  float(rs[0]) - float(ls[0]))
        else:
            theta_sh = 0.0

        if hip_ok:
            theta_hip = math.atan2(float(rh[1]) - float(lh[1]),
                                   float(rh[0]) - float(lh[0]))
        else:
            theta_hip = theta_sh  # no info → assume aligned

        delta_deg = math.degrees(theta_sh - theta_hip)
        while delta_deg >  180.0: delta_deg -= 360.0
        while delta_deg < -180.0: delta_deg += 360.0

        base_m = 0.0
        if la[0] > 0 and ra[0] > 0:
            base_px = math.hypot(float(ra[0]) - float(la[0]),
                                 float(ra[1]) - float(la[1]))
            base_m  = base_px / max(px_per_m, 1.0)

        result.update({'shoulder_angle_rad': theta_sh,
                       'hip_angle_rad':      theta_hip,
                       'torso_rotation_deg': delta_deg,
                       'base_width_m':       base_m,
                       'valid':              True})
    except Exception:
        pass
    return result


def detect_hook_arc(punch_history, min_pts=4) -> float:
    """
    Mide la curvatura azimutal del puño en el plano horizontal XZ usando la
    historia 3D ya disponible en Fighter.hL / Fighter.hR.

    Cada entrada del historial tiene 'pos3d': (X, Y, Z).
    Se proyecta sobre (X, Z) y se suman los cambios de dirección.

    Retorna ángulo total de cambio de dirección en grados.
    > HOOK_ARC_THR_DEG (25°) → trayectoria de gancho confirmada desde datos 3D.
    """
    pts = [(e['pos3d'][0], e['pos3d'][2])
           for e in punch_history
           if e.get('pos3d') and len(e['pos3d']) >= 3]
    if len(pts) < min_pts: return 0.0
    total = 0.0
    for i in range(1, len(pts) - 1):
        v1 = (pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1])
        v2 = (pts[i+1][0] - pts[i][0],  pts[i+1][1] - pts[i][1])
        n1 = math.hypot(*v1); n2 = math.hypot(*v2)
        if n1 < 1e-4 or n2 < 1e-4: continue
        cos_a = (v1[0]*v2[0] + v1[1]*v2[1]) / (n1 * n2)
        total += math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    return total


def torso_center_3d(pts3d):
    coords = [pts3d[i] for i in [5,6,11,12] if i in pts3d]
    if len(coords) < 2: return None
    return tuple(np.mean(coords, axis=0))

def hip_center_3d(pts3d):
    coords = [pts3d[i] for i in [11,12] if i in pts3d]
    if len(coords) < 1: return None
    return tuple(np.mean(coords, axis=0))

def dist3d(a, b):
    if a is None or b is None: return 0.0
    return math.sqrt(sum((float(a[i])-float(b[i]))**2 for i in range(3)))

def angle3pts(a, b, c):
    """Angle at point b in degrees, given 3D points a, b, c."""
    if a is None or b is None or c is None: return 0.0
    ba = np.array(a) - np.array(b); bc = np.array(c) - np.array(b)
    n1 = np.linalg.norm(ba); n2 = np.linalg.norm(bc)
    if n1 < 1e-6 or n2 < 1e-6: return 0.0
    cos_a = np.clip(np.dot(ba, bc) / (n1 * n2), -1.0, 1.0)
    return float(math.degrees(math.acos(cos_a)))

# ══════════════════════════════════════════════════════════════════
#  PROFESSIONAL BOXING SCORER  (IBF/WBC/WBA/WBO – 10-Must System)
# ══════════════════════════════════════════════════════════════════
class BoxingScorer:
    """
    Professional boxing round scoring aligned with IBF/WBC/WBA/WBO unified rules.

    Criteria (ref: Unified Rules of Boxing, McGill 2010, CompuBox protocol):
      1. Clean punches landed (face × 2.0, body × 1.0)
      2. Power punches (cross, hook, uppercut, overhand)
      3. Defense / ring generalship (slips/dodges, accuracy pressure)
      4. Aggressiveness (forward pressure, punch output)
    """

    @staticmethod
    def compute(fighter_stats: dict) -> dict:
        """
        Returns a rich scoring breakdown for one fighter in one round.
        fighter_stats keys: strikes, connected, face_hits, body_hits,
                            max_speed_ms, dodges, punch_types, aggression, agility
        """
        strikes   = fighter_stats.get('strikes', 0)
        connected = fighter_stats.get('connected', 0)
        face_hits = fighter_stats.get('face_hits', 0)
        body_hits = fighter_stats.get('body_hits', 0)
        dodges    = fighter_stats.get('dodges', 0)
        max_spd   = fighter_stats.get('max_speed_ms', 0.0)
        ptypes    = fighter_stats.get('punch_types', {})
        aggr      = fighter_stats.get('aggression', 0)
        agility   = fighter_stats.get('agility', 0.0)
        power_str = fighter_stats.get('power_strikes', 0)

        # ── 1. Clean punches ───────────────────────────────────────
        clean_pts  = face_hits * 2 + body_hits   # face weighted 2×

        # ── 2. Power punches ───────────────────────────────────────
        power_typed = sum(ptypes.get(t, 0) for t in POWER_PUNCH_TYPES)
        total_typed = max(sum(ptypes.values()), 1)
        power_pct   = power_typed / total_typed * 100

        # ── 3. Accuracy ────────────────────────────────────────────
        accuracy = connected / max(strikes, 1) * 100

        # ── 4. Defense ─────────────────────────────────────────────
        defense_sc = min(dodges * 4.0 + agility * 0.2, 30.0)

        # ── 5. Ring generalship (aggression + output) ──────────────
        ring_sc = min(aggr * 0.4 + (strikes / 45.0) * 10, 20.0)

        # ── 6. Speed bonus ─────────────────────────────────────────
        speed_sc = min(max_spd * 1.8, 15.0)

        # ── Composite score (raw, not normalized to 10) ────────────
        raw = (clean_pts * 1.5 + power_pct * 0.35 + accuracy * 0.45
               + defense_sc + ring_sc + speed_sc)

        return {
            'clean_punches_scored': clean_pts,
            'power_punches': power_typed,
            'power_pct': round(power_pct, 1),
            'jabs': ptypes.get('JAB', 0),
            'crosses': ptypes.get('CROSS', 0),
            'hooks': ptypes.get('HOOK', 0),
            'uppercuts': ptypes.get('UPPERCUT', 0),
            'overhands': ptypes.get('OVERHAND', 0),
            'body_shots': ptypes.get('BODYSHOT', 0),
            'accuracy_pct': round(accuracy, 1),
            'defense_score': round(defense_sc, 1),
            'ring_generalship': round(ring_sc, 1),
            'speed_bonus': round(speed_sc, 1),
            'raw_score': round(raw, 2),
        }

    @staticmethod
    def ten_must(raw_r: float, raw_b: float) -> tuple:
        """
        10-Must scoring system.
        Returns (pts_red, pts_blue).
        Dominant round (>15 pt gap in raw): 10-8.
        Close/slight edge: 10-9.
        Draw (<2 pt gap): 10-10.
        """
        diff = raw_r - raw_b
        if abs(diff) < 2.0:
            return 10, 10
        if diff > 0:   # red wins
            return 10, (8 if diff > 15 else 9)
        else:          # blue wins
            return (8 if abs(diff) > 15 else 9), 10

    @staticmethod
    def generate_scorecard_text(rnd: int, r_data: dict, b_data: dict,
                                r_score: dict, b_score: dict,
                                pts_r: int, pts_b: int) -> str:
        """
        CompuBox-style ASCII scorecard for one round.
        """
        winner_txt = ("EMPATE" if pts_r == pts_b
                      else ("ROJO" if pts_r > pts_b else "AZUL"))

        def col(d):
            return (f"  Golpes lanzados : {d.get('strikes',0):>4}\n"
                    f"  Golpes conectados: {d.get('connected',0):>4}  "
                    f"({d.get('accuracy_pct', r_score.get('accuracy_pct',0)):.0f}%)\n"
                    f"  Golpes de poder  : {r_score.get('power_punches',0) if d is r_data else b_score.get('power_punches',0):>4}  "
                    f"({r_score.get('power_pct',0.0) if d is r_data else b_score.get('power_pct',0.0):.0f}%)\n"
                    f"  Jabs / Cruces    : {(d.get('punch_types') or {}).get('JAB',0):>2} / "
                    f"{(d.get('punch_types') or {}).get('CROSS',0):<2}\n"
                    f"  Ganchos/Uppercuts: {(d.get('punch_types') or {}).get('HOOK',0):>2} / "
                    f"{(d.get('punch_types') or {}).get('UPPERCUT',0):<2}\n"
                    f"  Overhands / Body : {(d.get('punch_types') or {}).get('OVERHAND',0):>2} / "
                    f"{(d.get('punch_types') or {}).get('BODYSHOT',0):<2}\n"
                    f"  Cara / Cuerpo    : {d.get('face_hits',0):>2} / {d.get('body_hits',0):<2}\n"
                    f"  Vel. máx.        : {d.get('max_speed_ms',0.0):>5.2f} m/s\n"
                    f"  Esquivas         : {d.get('dodges',0):>4}\n"
                    f"  Postura          : {d.get('stance','?')}")

        r_col = col(r_data)
        b_col = col(b_data)

        lines = r_col.split('\n')
        b_lines = b_col.split('\n')
        # Side-by-side layout
        sep = "  │  "
        rows = []
        for l, r in zip(lines, b_lines):
            rows.append(f"{l:<38}{sep}{r}")

        header = (f"\n{'═'*82}\n"
                  f"  ROUND {rnd}  ─  TARJETA OFICIAL\n"
                  f"{'─'*82}\n"
                  f"  {'ESQUINA ROJA':<38}{'':3}{'ESQUINA AZUL'}\n"
                  f"{'─'*82}\n")
        footer = (f"\n{'─'*82}\n"
                  f"  PUNTOS ROJO : {pts_r}          "
                  f"PUNTOS AZUL : {pts_b}\n"
                  f"  ★  GANADOR ROUND {rnd}: {winner_txt}  ({pts_r}-{pts_b})\n"
                  f"{'═'*82}\n")
        return header + "\n".join(rows) + footer

    @staticmethod
    def compute_qualification(round_raw_scores: list) -> dict:
        """
        Aggregates per-round raw scores into a final session qualification grade.

        Grade scale (amateur boxing / sports-science performance reference):
          S  Élite          ≥ 85 pts
          A  Excelente      70 – 84 pts
          B  Bueno          55 – 69 pts
          C  Adecuado       40 – 54 pts
          D  En progreso    25 – 39 pts
          F  Necesita trabajo  < 25 pts
        """
        if not round_raw_scores:
            return {'grade': '—', 'score': 0.0, 'label': 'Sin datos',
                    'rounds_scored': 0, 'avg_raw': 0.0}
        avg = sum(round_raw_scores) / len(round_raw_scores)
        # Normalize to 0–100 (raw scores typically range 0–120)
        normalized = min(round(avg / 1.2, 1), 100.0)
        if   normalized >= 85: grade, label = 'S', 'Élite'
        elif normalized >= 70: grade, label = 'A', 'Excelente'
        elif normalized >= 55: grade, label = 'B', 'Bueno'
        elif normalized >= 40: grade, label = 'C', 'Adecuado'
        elif normalized >= 25: grade, label = 'D', 'En progreso'
        else:                  grade, label = 'F', 'Necesita trabajo'
        return {
            'grade':         grade,
            'score':         normalized,
            'label':         label,
            'rounds_scored': len(round_raw_scores),
            'avg_raw':       round(avg, 2),
        }

class AggressivenessScorer:
    """
    Scoring oficial para sesiones de pelea (ROJO vs AZUL).
    Criterios: agresividad (presión, movimiento) + evasión (esquivas, agilidad).
    Los conteos de golpes NO forman parte del puntaje para evitar discrepancias
    con el arbitraje manual y la polémica en la comunidad.
    """

    @staticmethod
    def compute(fighter_stats: dict) -> dict:
        aggr    = fighter_stats.get('aggression', 0)
        agility = fighter_stats.get('agility', 0.0)
        dodges  = fighter_stats.get('dodges', 0)
        max_spd = fighter_stats.get('max_speed_ms', 0.0)
        # ── Agresividad: presión + actividad en el ring ────────────────
        aggr_sc = min(aggr * 0.6 + max_spd * 1.5, 60.0)
        # ── Evasión: movimiento de cabeza + índice de agilidad ─────────
        evad_sc = min(dodges * 3.5 + agility * 0.4, 40.0)
        raw = aggr_sc + evad_sc
        return {
            'aggr_score':    round(aggr_sc, 1),
            'evasion_score': round(evad_sc, 1),
            'raw_score':     round(raw, 2),
        }

    @staticmethod
    def ten_must(raw_r: float, raw_b: float) -> tuple:
        diff = raw_r - raw_b
        if abs(diff) < 2.0: return 10, 10
        if diff > 0: return 10, (8 if diff > 15 else 9)
        else:        return (8 if abs(diff) > 15 else 9), 10

    @staticmethod
    def compute_qualification(round_raw_scores: list) -> dict:
        """
        Calificación de sesión para FIGHT mode.
        Los raw_scores de AggressivenessScorer ya están en rango 0-100,
        por lo que NO se divide por 1.2 (a diferencia de BoxingScorer).
        """
        if not round_raw_scores:
            return {'grade': '—', 'score': 0.0, 'label': 'Sin datos',
                    'rounds_scored': 0, 'avg_raw': 0.0}
        avg = sum(round_raw_scores) / len(round_raw_scores)
        normalized = min(round(avg, 1), 100.0)   # ya está en 0-100
        if   normalized >= 85: grade, label = 'S', 'Élite'
        elif normalized >= 70: grade, label = 'A', 'Excelente'
        elif normalized >= 55: grade, label = 'B', 'Bueno'
        elif normalized >= 40: grade, label = 'C', 'Adecuado'
        elif normalized >= 25: grade, label = 'D', 'En progreso'
        else:                  grade, label = 'F', 'Necesita trabajo'
        return {
            'grade':         grade,
            'score':         normalized,
            'label':         label,
            'rounds_scored': len(round_raw_scores),
            'avg_raw':       round(avg, 2),
        }

    @staticmethod
    def generate_scorecard_text(rnd: int, r_data: dict, b_data: dict,
                                r_sc: dict, b_sc: dict,
                                pts_r: int, pts_b: int) -> str:
        winner_txt = ("EMPATE" if pts_r == pts_b
                      else ("ROJO" if pts_r > pts_b else "AZUL"))

        def col(data, sc):
            return (f"  Agresividad      : {data.get('aggression',0):>4}  "
                    f"(sc {sc.get('aggr_score',0):.1f})\n"
                    f"  Velocidad máx.   : {data.get('max_speed_ms',0.0):>5.2f} m/s\n"
                    f"  Evasiones        : {data.get('dodges',0):>4}  "
                    f"(sc {sc.get('evasion_score',0):.1f})\n"
                    f"  Agilidad         : {data.get('agility',0.0):>5.1f}\n"
                    f"  Postura          : {data.get('stance','?')}")

        lines   = col(r_data, r_sc).split('\n')
        b_lines = col(b_data, b_sc).split('\n')
        sep = "  │  "
        rows = [f"{l:<38}{sep}{r}" for l, r in zip(lines, b_lines)]
        header = (f"\n{'═'*82}\n"
                  f"  ROUND {rnd}  ─  TARJETA OFICIAL  [MODO PELEA · Agresividad + Evasión]\n"
                  f"{'─'*82}\n"
                  f"  {'ESQUINA ROJA':<38}{sep}{'ESQUINA AZUL'}\n"
                  f"{'─'*82}\n")
        footer = (f"\n{'─'*82}\n"
                  f"  PUNTOS ROJO : {pts_r}    PUNTOS AZUL : {pts_b}\n"
                  f"  ★  GANADOR ROUND {rnd}: {winner_txt}  ({pts_r}-{pts_b})\n"
                  f"{'═'*82}\n")
        return header + "\n".join(rows) + footer


SKELETON_PAIRS = [
    (5,6),(5,7),(7,9),(6,8),(8,10),
    (5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16),
    (0,1),(0,2),(1,3),(2,4),(0,5),(0,6),
]

def draw_skeleton(img, kp, color=WHT, alpha=0.7):
    h, w = img.shape[:2]
    for a, b in SKELETON_PAIRS:
        if a >= len(kp) or b >= len(kp): continue
        ax,ay = int(kp[a][0]),int(kp[a][1])
        bx,by = int(kp[b][0]),int(kp[b][1])
        if ax==0 and ay==0: continue
        if bx==0 and by==0: continue
        if not (0<=ax<w and 0<=ay<h and 0<=bx<w and 0<=by<h): continue
        cv2.line(img, (ax,ay), (bx,by), color, 1, cv2.LINE_AA)
    for i, (kx, ky) in enumerate(kp):
        kx,ky = int(kx),int(ky)
        if kx==0 and ky==0: continue
        if not (0<=kx<w and 0<=ky<h): continue
        r = 4 if i in (9,10) else 2
        cv2.circle(img, (kx,ky), r, color, -1)

# ══════════════════════════════════════════════════════════════════
#  [9] DATASET CAPTURE
# ══════════════════════════════════════════════════════════════════
class DatasetCapture:
    def __init__(self):
        self._enabled = False
        self._session_dir: pathlib.Path = None
        self._csv_file = None
        self._csv_writer = None
        self._frame_count = 0
        self._lock = threading.Lock()

    def start_session(self):
        DATASET_DIR.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_dir = DATASET_DIR / ts
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._csv_file = open(self._session_dir / "events.csv", 'w', newline='')
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            'timestamp','fighter','hand','punch_type','speed_ms',
            'extension_m','hit','face_hit','body_hit',
            'elbow_angle','shoulder_x','shoulder_y','shoulder_z'
        ])
        self._enabled = True
        self._frame_count = 0
        print(f"[DATASET] Session started → {self._session_dir}")

    def stop_session(self):
        self._enabled = False
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None

    def log_event(self, fighter, hand, punch_type, speed, ext, hit, face_hit, body_hit,
                  elbow_angle=0.0, shoulder_3d=None):
        if not self._enabled or self._csv_writer is None: return
        sx = sy = sz = 0.0
        if shoulder_3d: sx, sy, sz = shoulder_3d
        with self._lock:
            self._csv_writer.writerow([
                time.time(), fighter, hand, punch_type,
                round(speed, 3), round(ext, 3), int(hit), int(face_hit), int(body_hit),
                round(elbow_angle, 1), round(sx, 3), round(sy, 3), round(sz, 3)
            ])

    def save_frame(self, frame, label=""):
        if not self._enabled or self._session_dir is None: return
        self._frame_count += 1
        fname = self._session_dir / f"frame_{self._frame_count:06d}_{label}.jpg"
        cv2.imwrite(str(fname), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

DATASET = DatasetCapture()

# ══════════════════════════════════════════════════════════════════
#  [8] FIGHTERID API EXPORT
# ══════════════════════════════════════════════════════════════════
from fighterid_supabase_bridge import FighterIDAPI
FAPI = FighterIDAPI()

# ══════════════════════════════════════════════════════════════════
#  LIVE STREAM: Supabase + RTMP (FFmpeg)
# ══════════════════════════════════════════════════════════════════

def _load_stream_config():
    """Carga credenciales de fighterid_stream.json al arrancar."""
    global SUPABASE_URL, SUPABASE_ANON_KEY, STREAM_RTMP_URL, STREAM_FPS_TARGET
    try:
        if _STREAM_CFG_FILE.exists():
            cfg = json.loads(_STREAM_CFG_FILE.read_text(encoding='utf-8'))
            SUPABASE_URL      = cfg.get('supabase_url',      SUPABASE_URL)
            SUPABASE_ANON_KEY = cfg.get('supabase_anon_key', SUPABASE_ANON_KEY)
            STREAM_RTMP_URL   = cfg.get('stream_rtmp_url',   STREAM_RTMP_URL)
            STREAM_FPS_TARGET = int(cfg.get('stream_fps',    STREAM_FPS_TARGET))
    except Exception as e:
        print(f"[stream_cfg] No se pudo cargar config: {e}")

def _save_stream_config():
    """Persiste credenciales en fighterid_stream.json."""
    try:
        cfg = {
            'supabase_url':      SUPABASE_URL,
            'supabase_anon_key': SUPABASE_ANON_KEY,
            'stream_rtmp_url':   STREAM_RTMP_URL,
            'stream_fps':        STREAM_FPS_TARGET,
        }
        _STREAM_CFG_FILE.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"[stream_cfg] No se pudo guardar config: {e}")

_load_stream_config()   # cargar al importar el módulo


class SupabaseStreamer:
    """
    Envía estadísticas en vivo a Supabase via REST API (compatible con Realtime).
    El frontend se suscribe a cambios en la tabla live_session y recibe
    actualizaciones automáticas sin polling.
    """
    _HDRS_BASE = {
        'Content-Type':  'application/json',
        'Prefer':        'resolution=merge-duplicates,return=minimal',
    }

    def __init__(self):
        self._q      = deque(maxlen=300)
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="SupabaseStreamer")
        self._thread.start()
        self.push_ok  = 0
        self.push_err = 0

    def _headers(self) -> dict:
        return {**self._HDRS_BASE,
                'apikey':        SUPABASE_ANON_KEY,
                'Authorization': f'Bearer {SUPABASE_ANON_KEY}'}

    def _worker(self):
        while True:
            if not self._q:
                time.sleep(0.08); continue
            task = self._q.popleft()
            if not SUPABASE_URL or not SUPABASE_ANON_KEY:
                continue
            try:
                url  = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{task['table']}"
                meth = task.get('method', 'POST')
                r    = requests.post(url, json=task['data'],
                                     headers=self._headers(), timeout=6)
                if r.status_code in (200, 201): self.push_ok  += 1
                else:                           self.push_err += 1
            except Exception:
                self.push_err += 1

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _clean(d: dict) -> dict:
        """Convierte deques y filtra callables para serialización JSON."""
        out = {}
        for k, v in d.items():
            if callable(v):                continue
            if isinstance(v, deque):       out[k] = list(v)
            elif isinstance(v, dict):      out[k] = SupabaseStreamer._clean(v)
            else:                          out[k] = v
        return out

    def push_live_stats(self, session_id: str, stats: dict):
        """Upsert estado actual de la pelea en live_session."""
        if not session_id: return
        payload = {
            'session_id':      session_id,
            'state':           stats.get('state', 'IDLE'),
            'phase':           stats.get('phase', 'IDLE'),
            'round_num':       stats.get('rnd', 0),
            'timer_remaining': stats.get('rem', 0),
            'scoring_mode':    stats.get('mode', 'fight'),
            'is_test':         stats.get('mode_tm', False),
            'eng_fps':         round(stats.get('eng_fps', 0.0), 1),
            'red':             self._clean(stats.get('red',  {})),
            'blue':            self._clean(stats.get('blue', {})),
            'updated_at':      datetime.datetime.utcnow().isoformat() + 'Z',
        }
        self._q.append({'method': 'POST', 'table': SUPABASE_TABLE_LIVE,
                        'data': payload})

    def push_round_result(self, session_id: str, rnd: int, data: dict):
        """Inserta resultado de un round completado en round_results."""
        payload = {
            'session_id': session_id,
            'round_num':  rnd,
            'mode':       data.get('mode',     data.get('scoring', 'fight')),
            'winner':     data.get('winner',   ''),
            'scorecard':  self._clean(data.get('scorecard', {})),
            'red_stats':  self._clean(data.get('red',  {})),
            'blue_stats': self._clean(data.get('blue', {})),
            'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
        }
        self._q.append({'method': 'POST', 'table': SUPABASE_TABLE_ROUNDS,
                        'data': payload})

    def push_session_end(self, session_id: str, summary: dict):
        """Marca la sesión como ENDED con el resumen final."""
        payload = {
            'session_id': session_id,
            'state':      'ENDED',
            'phase':      'IDLE',
            'summary':    self._clean(summary),
            'updated_at': datetime.datetime.utcnow().isoformat() + 'Z',
        }
        self._q.append({'method': 'POST', 'table': SUPABASE_TABLE_LIVE,
                        'data': payload})


class VideoStreamer:
    """
    Codifica frames procesados (con overlay) y los envía via RTMP usando FFmpeg.
    Compatible con YouTube Live, Twitch, Cloudflare Stream, Mux o cualquier
    servidor RTMP propio (Nginx-RTMP, SRS, etc.).
    Requiere FFmpeg instalado en el sistema: https://ffmpeg.org/download.html
    """

    def __init__(self):
        self._proc:   subprocess.Popen | None = None
        self._active: bool = False
        self._w = CAM_W; self._h = CAM_H

    def start(self, rtmp_url: str, fps: int = 30,
              width: int = 1920, height: int = 1080) -> tuple[bool, str]:
        """Inicia el proceso FFmpeg. Retorna (ok, mensaje)."""
        if not rtmp_url:
            return False, "URL RTMP vacía"
        self.stop()
        self._w = width; self._h = height
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            # Entrada: frames raw en pipe stdin
            '-f', 'rawvideo', '-pix_fmt', 'bgr24',
            '-s', f'{width}x{height}',
            '-r', str(fps),
            '-i', 'pipe:0',
            # Codec: H.264 ultra-fast para mínima latencia
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-tune', 'zerolatency',
            '-b:v', '4M', '-maxrate', '4M', '-bufsize', '8M',
            '-g', str(fps * 2),   # GOP 2s — recomendado para streaming
            '-pix_fmt', 'yuv420p',
            '-f', 'flv',
            rtmp_url,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._active = True
            return True, f"FFmpeg iniciado → {rtmp_url}"
        except FileNotFoundError:
            return False, "FFmpeg no encontrado — instala ffmpeg.org"
        except Exception as e:
            return False, f"Error FFmpeg: {e}"

    def send_frame(self, bgr_frame) -> bool:
        """Escribe un frame al pipe de FFmpeg."""
        if not self._active or self._proc is None: return False
        try:
            h, w = bgr_frame.shape[:2]
            if w != self._w or h != self._h:
                bgr_frame = cv2.resize(bgr_frame, (self._w, self._h),
                                       interpolation=cv2.INTER_LINEAR)
            self._proc.stdin.write(bgr_frame.tobytes())
            return True
        except (BrokenPipeError, OSError):
            self._active = False
            return False

    def stop(self):
        self._active = False
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=4)
            except Exception: pass
            self._proc = None

    @property
    def is_running(self) -> bool:
        return self._active and self._proc is not None and \
               self._proc.poll() is None


# Instancias globales — controladas desde la GUI
SUPA  = SupabaseStreamer()
VSTRM = VideoStreamer()


class LiveStreamManager(threading.Thread):
    """
    Hilo de fondo que conecta el VisionEngine con Supabase y FFmpeg/RTMP.

    Responsabilidades:
      · Cada STATS_INTERVAL segundos: upsert stats en live en Supabase.
      · Al detectar nuevo winner en rnd_winners: push round_result.
      · Si VideoStreamer activo: alimentar con frames procesados a target FPS.
    """
    STATS_INTERVAL = 1.5   # segundos entre pushes de stats

    def __init__(self, engine: 'VisionEngine'):
        super().__init__(daemon=True, name="LiveStreamMgr")
        self._engine          = engine
        # Use the web's session_id if already known; fallback to timestamp-based ID
        # (never generate a uuid4 locally — the web is the source of truth)
        self._session_id      = FAPI._session_id or f"fs_{int(time.time())}"
        self._last_push_t     = 0.0
        self._seen_rnd_winners: dict = {}
        self._stop_ev         = threading.Event()
        # Publicar sesión como INIT en Supabase
        SUPA.push_live_stats(self._session_id,
                             {'state': 'INIT', 'phase': 'IDLE', 'rnd': 0,
                              'rem': 0, 'mode': 'fight', 'mode_tm': False,
                              'eng_fps': 0.0, 'red': {}, 'blue': {}})

    def run(self):
        frame_interval = 1.0 / max(STREAM_FPS_TARGET, 1)
        last_frame_t   = 0.0

        while not self._stop_ev.is_set():
            now    = time.time()
            stats  = self._engine.get_stats()

            # ── Stats push ────────────────────────────────────────
            if stats and (now - self._last_push_t) >= self.STATS_INTERVAL:
                SUPA.push_live_stats(self._session_id, stats)
                self._last_push_t = now
                # Detectar nuevos rounds completados
                rw = stats.get('rnd_winners', {})
                for rnd, winner in rw.items():
                    if rnd not in self._seen_rnd_winners:
                        rdata = self._engine.get_round_stats().get(rnd, {})
                        SUPA.push_round_result(self._session_id, rnd, rdata)
                        self._seen_rnd_winners[rnd] = winner

            # ── Video frame ───────────────────────────────────────
            if VSTRM.is_running and (now - last_frame_t) >= frame_interval:
                fa, _, _ = self._engine.get_frames()
                if fa is not None:
                    VSTRM.send_frame(fa)
                last_frame_t = now

            time.sleep(0.010)   # ~100Hz de polling máximo

    def stop(self, summary: dict | None = None):
        if summary:
            SUPA.push_session_end(self._session_id, summary)
        self._stop_ev.set()

    @property
    def session_id(self) -> str:
        return self._session_id


# ══════════════════════════════════════════════════════════════════
#  HEAD TRACKER
# ══════════════════════════════════════════════════════════════════
class HeadTracker:
    def __init__(self):
        self.hist = deque(maxlen=24)
        self.prev_pos3d = self.prev_t = None
        self.total_d = self.max_spd = 0.0
        self.dodges = 0; self._dodging = False
        self.cur_spd = 0.0; self.last_pos3d = self.last_pos2d = None

    def reset(self):
        self.hist.clear(); self.prev_pos3d = self.prev_t = None
        self.total_d = self.max_spd = 0.0
        self.dodges = 0; self._dodging = False
        self.cur_spd = 0.0; self.last_pos3d = self.last_pos2d = None

    def update(self, pos3d, pos2d, t):
        self.last_pos3d = pos3d; self.last_pos2d = pos2d; spd = 0.0
        if self.prev_pos3d is not None:
            dt = t - self.prev_t
            if dt > 0.001:
                d = dist3d(pos3d, self.prev_pos3d); spd = d/dt; self.total_d += d
                if spd > self.max_spd: self.max_spd = spd
                if spd > DODGE_SPD_MS:
                    if not self._dodging: self.dodges += 1; self._dodging = True
                else: self._dodging = False
        self.hist.append({'pos3d': pos3d, 'time': t})
        self.prev_pos3d = pos3d; self.prev_t = t; self.cur_spd = spd

    def agility(self):
        return round(min(self.total_d*8,40) + min(self.max_spd*8,35) + min(self.dodges*2.5,25), 1)

# ══════════════════════════════════════════════════════════════════
#  [5] IMPROVED BIOMECHANICAL PUNCH CLASSIFIER
# ══════════════════════════════════════════════════════════════════
class Fighter:
    def __init__(self, name, col):
        self.name = name; self.col = col
        self.strikes = self.connected = self.aggr = self.face_hits = self.body_hits = 0
        self.max_spd_ms = self.max_ext_m = 0.0
        self.hL = deque(maxlen=HISTORY_LEN); self.hR = deque(maxlen=HISTORY_LEN)
        self.pL = self.pR = self.pt = None
        self.punchL = self.punchR = False; self.tL = self.tR = self.mL = self.mR = 0.0
        self.ptypes = {"JAB":0,"CROSS":0,"HOOK":0,"UPPERCUT":0,"OVERHAND":0,"BODYSHOT":0}
        self.head = HeadTracker(); self._lfht = 0.0
        self.spd_history = deque(maxlen=60)
        # 3D keypoints for biomechanics (updated each frame)
        self.pts3d: dict = {}
        # ── Professional boxing additions ──────────────────────────
        self.power_strikes = 0          # punches classified as CROSS/HOOK/UPPERCUT/OVERHAND
        self.stance: str   = "unknown"  # "orthodox" | "southpaw" | "unknown"
        self.combo_count   = 0          # number of combinations thrown (≥2 punches within COMBO_WINDOW_S)
        self._last_punch_t = 0.0        # timestamp of last punch (for combo detection)
        self._in_combo     = False
        self._combo_n      = 0          # consecutive punches in current combo
        # glove status (bare=True means bare hand detected at wrist)
        self.glove_detected = True      # default assume gloves until proven otherwise
        # ── Biomechanical quality metrics ──────────────────────────
        self.punch_left_count  = 0       # per-side count for load balance
        self.punch_right_count = 0
        self._kinetic_scores   = deque(maxlen=20)  # kinetic chain quality per punch
        # ── Overhead camera data (CAM C cenital) ───────────────────
        self.overhead_bio: dict = {}     # last result of extract_overhead_biomechanics()

    def reset(self):
        self.strikes = self.connected = self.aggr = self.face_hits = self.body_hits = 0
        self.max_spd_ms = self.max_ext_m = 0.0
        self.hL.clear(); self.hR.clear()
        self.pL = self.pR = self.pt = None
        self.punchL = self.punchR = False; self.tL = self.tR = self.mL = self.mR = 0.0
        self.ptypes = {"JAB":0,"CROSS":0,"HOOK":0,"UPPERCUT":0,"OVERHAND":0,"BODYSHOT":0}
        self.head.reset(); self._lfht = 0.0; self.spd_history.clear()
        self.power_strikes = 0; self.combo_count = 0
        self._last_punch_t = 0.0; self._in_combo = False; self._combo_n = 0
        self.punch_left_count = 0; self.punch_right_count = 0
        self._kinetic_scores.clear()

    def detect_stance(self):
        """
        Orthodox:  hombro derecho más atrás (mayor Z), izquierdo adelante.
        Southpaw:  hombro izquierdo más atrás, derecho adelante.
        Usa ángulo real de hombros desde CAM C cenital cuando disponible;
        si no, diferencia Z desde cámaras laterales.
        """
        # Opción 1: ángulo real desde vista cenital (mucho más preciso)
        if self.overhead_bio.get('valid'):
            sh_ang_deg = math.degrees(self.overhead_bio['shoulder_angle_rad'])
            # Ortodoxo: hombro izquierdo al frente → eje de hombros inclinado (+)
            if sh_ang_deg > 10.0:   self.stance = "orthodox"
            elif sh_ang_deg < -10.0: self.stance = "southpaw"
            return
        # Fallback: diferencia de profundidad Z desde laterales
        ls, rs = self.pts3d.get(5), self.pts3d.get(6)
        if ls is None or rs is None:
            self.stance = "unknown"; return
        diff = float(ls[2]) - float(rs[2])   # Z-axis depth difference L vs R
        if diff < -STANCE_THRESH_M:
            self.stance = "orthodox"
        elif diff > STANCE_THRESH_M:
            self.stance = "southpaw"
        # else keep previous stance

    def accuracy(self):
        return round(self.connected / max(1, self.strikes) * 100, 1)

    def _elbow_angle(self, left: bool) -> float:
        """Angle at elbow: shoulder–elbow–wrist."""
        p3 = self.pts3d
        if left:
            sh, el, wr = p3.get(5), p3.get(7), p3.get(9)
        else:
            sh, el, wr = p3.get(6), p3.get(8), p3.get(10)
        return angle3pts(sh, el, wr)

    def _shoulder_rotation(self) -> float:
        """
        Rotation proxy from lateral cameras: X-axis diff L vs R shoulder.
        Used as fallback when overhead camera is unavailable.
        """
        p3 = self.pts3d
        ls, rs = p3.get(5), p3.get(6)
        if ls is None or rs is None: return 0.0
        return float(ls[0] - rs[0])

    def _hip_rotation(self) -> float:
        """X-axis diff L vs R hip (lateral camera fallback)."""
        p3 = self.pts3d
        lh, rh = p3.get(11), p3.get(12)
        if lh is None or rh is None: return 0.0
        return float(lh[0] - rh[0])

    def shoulder_rotation_deg(self) -> float:
        """
        Ángulo real del eje de hombros en el plano horizontal (grados).
        Usa datos de CAM C cenital cuando disponible; si no, proyección lateral.
        """
        if self.overhead_bio.get('valid'):
            return math.degrees(self.overhead_bio['shoulder_angle_rad'])
        # Fallback: ángulo estimado desde cámara lateral (pts3d de A+B)
        p3 = self.pts3d
        ls, rs = p3.get(5), p3.get(6)
        if ls is None or rs is None: return 0.0
        return math.degrees(math.atan2(float(rs[2]) - float(ls[2]),
                                       float(rs[0]) - float(ls[0])))

    def torso_rotation_deg(self) -> float:
        """
        Separación angular hombro-cadera (cadena cinética) en grados.
        Usa datos de CAM C cenital cuando disponible.
        Positivo → hombros adelantados respecto a caderas.
        """
        if self.overhead_bio.get('valid'):
            return self.overhead_bio['torso_rotation_deg']
        # Fallback crudo: diferencia de offsets X laterales
        sh = self._shoulder_rotation(); hip = self._hip_rotation()
        if abs(sh) < 0.001 and abs(hip) < 0.001: return 0.0
        return math.degrees(math.atan2(sh - hip, max(abs(sh), abs(hip), 0.001))) * 10.0

    def _kinetic_chain_quality(self) -> float:
        """
        Cadena cinética: 0.0 (mala técnica) – 1.0 (excelente).
        Con CAM C cenital usa ángulos reales; si no, offset lateral.
        Boxeo profesional: cadera y hombro rotan en la misma dirección,
        cadera lidera y hombro amplifica (ratio ideal ≈ 1.0–1.5).
        """
        if self.overhead_bio.get('valid'):
            # Ángulos reales desde vista cenital
            sh_ang  = self.overhead_bio['shoulder_angle_rad']
            hip_ang = self.overhead_bio['hip_angle_rad']
            rot_deg = abs(self.overhead_bio['torso_rotation_deg'])
            if rot_deg < 2.0: return 0.0          # Sin rotación detectable
            same_dir = (math.cos(sh_ang) * math.cos(hip_ang) +
                        math.sin(sh_ang) * math.sin(hip_ang)) > 0
            # Más rotación de torso = mejor cadena cinética (hasta 45°)
            quality = min(rot_deg / 45.0, 1.0)
            return round(quality if same_dir else quality * 0.3, 2)
        # Fallback lateral
        sh_rot  = self._shoulder_rotation()
        hip_rot = self._hip_rotation()
        if abs(sh_rot) < 0.01 and abs(hip_rot) < 0.01: return 0.0
        if abs(hip_rot) < 0.01: return 0.5
        coordinated = (sh_rot * hip_rot) > 0
        ratio = min(abs(sh_rot) / (abs(hip_rot) + 0.001), 2.0) / 2.0
        return round(0.6 + 0.4 * ratio if coordinated else 0.2 * ratio, 2)

    def punch_balance(self) -> float:
        """
        Left/right punch balance: 1.0 = perfectly balanced, 0.0 = all one side.
        """
        total = self.punch_left_count + self.punch_right_count
        if total == 0: return 0.0
        minor = min(self.punch_left_count, self.punch_right_count)
        return round(minor / total * 2, 2)

    def kinetic_chain_avg(self) -> float:
        """Average kinetic chain quality across the last 20 punches."""
        if not self._kinetic_scores: return 0.0
        return round(float(np.mean(list(self._kinetic_scores))), 2)

    def _classify(self, wp3, sp3, left, vel3, dur, mx,
                  arc_deg: float = 0.0) -> str:
        """
        Clasifica el tipo de golpe usando biomecánica 3D.

        arc_deg  — curvatura del puño en el plano XZ (detect_hook_arc).
                   Fuente primaria para confirmar HOOK independientemente de la
                   cámara lateral.
        El método usa self.overhead_bio para ángulos de rotación reales cuando
        CAM C cenital está disponible.
        """
        if sp3 is None: return "UNKNOWN"
        vx, vy, vz = vel3
        spd = math.sqrt(vx*vx + vy*vy + vz*vz)
        if spd < 0.01: return "UNKNOWN"

        # Dirección normalizada (azimut estable: atan2 en vez de división cruda)
        vyn      = vy / spd                                    # componente vertical norm.
        azimuth  = math.degrees(math.atan2(abs(vx), abs(vz))) # 0°=recto, 90°=lateral
        hdiff    = sp3[1] - wp3[1]                            # hombro más alto que muñeca → positivo

        elbow    = self._elbow_angle(left)
        # Rotación de torso desde fuente más precisa disponible
        rot_deg  = self.torso_rotation_deg()

        # ── 1. BODYSHOT: muñeca significativamente por debajo del hombro ───────
        if hdiff > 0.25 and wp3[1] > sp3[1] + 0.15:
            return "BODYSHOT"

        # ── 2. UPPERCUT: trayectoria ascendente + codo doblado ─────────────────
        elbow_bent = (elbow < 120) if elbow > 0 else (azimuth < 45)
        if vyn < -0.4 and hdiff < 0.1 and elbow_bent:
            return "UPPERCUT"

        # ── 3. HOOK / OVERHAND ─────────────────────────────────────────────────
        # Confirmación por arco 3D (detect_hook_arc) O por azimut lateral + codo
        hook_by_arc   = arc_deg >= HOOK_ARC_THR_DEG
        hook_by_angle = azimuth > 40.0 and (elbow < 140 or elbow == 0)
        if hook_by_arc or hook_by_angle:
            return ("OVERHAND"
                    if vyn > 0.2 and mx > EXTENSION_THR_M * 1.8 and dur > 0.18
                    else "HOOK")

        # ── 4. JAB / CROSS: golpe recto (azimut bajo = rumbo frontal) ──────────
        straight = azimuth < 35.0    # menos de 35° de desviación lateral
        if straight:
            if left:
                if dur < 0.28 and mx > EXTENSION_THR_M * 1.4: return "JAB"
            else:
                # CROSS requiere rotación de torso notable (confirma potencia)
                if mx > EXTENSION_THR_M * 1.5:
                    return "CROSS"

        # ── 5. Fallback: si hay rotación significativa de torso → CROSS/JAB ─────
        if abs(rot_deg) > 10.0:
            return "CROSS" if not left else "JAB"
        return "JAB" if left else "CROSS"

    def update_punch(self, wp3, left, sp3, t):
        hist  = self.hL if left else self.hR
        prev3 = self.pL if left else self.pR
        active = self.punchL if left else self.punchR
        ext = dist3d(wp3, sp3) if sp3 else 0.0
        vel3 = (0.0, 0.0, 0.0); spd = 0.0
        hist.append({'pos3d': wp3, 'time': t, 'ext': ext})
        if prev3 and self.pt:
            dt = t - self.pt
            if dt > 0.001:
                dvx=wp3[0]-prev3[0]; dvy=wp3[1]-prev3[1]; dvz=wp3[2]-prev3[2]
                spd = math.sqrt(dvx*dvx+dvy*dvy+dvz*dvz)/dt
                vel3 = (dvx/dt, dvy/dt, dvz/dt)
        hl = len(hist)
        if hl >= 3:
            # Velocidad y dirección windowed (2 segmentos) — consistentes entre sí
            rec=list(hist); sw=[]; wvx=[]; wvy=[]; wvz=[]
            for a,b in ((rec[-3],rec[-2]),(rec[-2],rec[-1])):
                dtw = b['time'] - a['time']
                if dtw > 0.001:
                    ddx=b['pos3d'][0]-a['pos3d'][0]
                    ddy=b['pos3d'][1]-a['pos3d'][1]
                    ddz=b['pos3d'][2]-a['pos3d'][2]
                    sw.append(math.sqrt(ddx*ddx+ddy*ddy+ddz*ddz)/dtw)
                    wvx.append(ddx/dtw); wvy.append(ddy/dtw); wvz.append(ddz/dtw)
            if sw:
                spd  = float(np.mean(sw))
                vel3 = (float(np.mean(wvx)), float(np.mean(wvy)), float(np.mean(wvz)))
        spd = min(spd, PUNCH_SPD_CAP_MS)
        if spd > self.max_spd_ms: self.max_spd_ms = spd
        if ext > self.max_ext_m:  self.max_ext_m  = ext
        self.spd_history.append(spd)
        new_p = False; ptype = "UNKNOWN"
        if hl >= 3:
            if spd > PUNCH_SPD_THR_MS and ext > EXTENSION_THR_M and not active:
                if left: self.punchL=True; self.tL=t; self.mL=ext
                else:    self.punchR=True; self.tR=t; self.mR=ext
            elif active:
                if left:
                    if ext > self.mL: self.mL = ext
                    cur = self.mL; dur = t - self.tL
                else:
                    if ext > self.mR: self.mR = ext
                    cur = self.mR; dur = t - self.tR
                retracted = ext < cur * RETRACTION_RATIO
                slow      = spd < PUNCH_SPD_THR_MS * 0.7
                dur_ok    = MIN_PUNCH_DUR < dur < MAX_PUNCH_DUR
                peak_ok   = cur > EXTENSION_THR_M * 1.1   # 1.3→1.1: umbral de pico más accesible
                # OR lógico: basta con que el puño retroceda O desacelere (antes se requería AMBOS)
                if (retracted or slow) and dur_ok and peak_ok:
                    av3 = vel3
                    if hl >= 4:
                        seg=list(hist)[-4:]; vxs=[]; vys=[]; vzs=[]
                        for i in range(len(seg)-1):
                            dt2 = seg[i+1]['time'] - seg[i]['time']
                            if dt2 > 0.001:
                                vxs.append((seg[i+1]['pos3d'][0]-seg[i]['pos3d'][0])/dt2)
                                vys.append((seg[i+1]['pos3d'][1]-seg[i]['pos3d'][1])/dt2)
                                vzs.append((seg[i+1]['pos3d'][2]-seg[i]['pos3d'][2])/dt2)
                        if vxs: av3=(float(np.mean(vxs)),float(np.mean(vys)),float(np.mean(vzs)))
                    new_p=True; self.strikes+=1; self.aggr+=1
                    arc_deg = detect_hook_arc(list(hist))
                    ptype = self._classify(wp3, sp3, left, av3, dur, cur,
                                           arc_deg=arc_deg)
                    if ptype in self.ptypes: self.ptypes[ptype] += 1
                    # ── Power punch tracking ───────────────────────
                    if ptype in POWER_PUNCH_TYPES:
                        self.power_strikes += 1
                    # ── Combination tracking ───────────────────────
                    if t - self._last_punch_t <= COMBO_WINDOW_S:
                        self._combo_n += 1
                        if self._combo_n == 2:    # second punch = combo starts
                            self.combo_count += 1
                    else:
                        self._combo_n = 1         # reset, this is first punch of new window
                    self._last_punch_t = t
                    # ── Biomechanical quality ─────────────────────
                    self._kinetic_scores.append(self._kinetic_chain_quality())
                    if left: self.punch_left_count  += 1
                    else:    self.punch_right_count += 1
                    # ── Stance update per punch ────────────────────
                    self.detect_stance()
                    if left: self.punchL=False; self.mL=0.0
                    else:    self.punchR=False; self.mR=0.0
                elif dur >= MAX_PUNCH_DUR:
                    if left: self.punchL=False; self.mL=0.0
                    else:    self.punchR=False; self.mR=0.0
        if left: self.pL = wp3
        else:    self.pR = wp3
        self.pt = t
        return new_p, spd, ptype, active

# ══════════════════════════════════════════════════════════════════
#  ROLE DETECTOR
# ══════════════════════════════════════════════════════════════════
class RoleDetector:
    """
    Detección de roles basada en condiciones visuales:
      - MODO PRUEBA  : 1 persona con guantes BLANCOS + torso descubierto (sin camiseta)
      - SESIÓN NORMAL: 2 personas con guantes de box (cualquier color) +
                       al menos UNA con camiseta NEGRA (→ esquina ROJA);
                       la otra persona → esquina AZUL
    """
    def __init__(self):
        self._wins = {}; self.locked = False
        self.test_pid = self.red_pid = self.blue_pid = None; self.mode = "none"

    def _ensure(self, pid):
        if pid not in self._wins:
            self._wins[pid] = {
                'W':  deque(maxlen=VOTE_WINDOW),   # guantes blancos + torso descubierto
                'R':  deque(maxlen=VOTE_WINDOW),   # guantes rojos  (legacy)
                'B':  deque(maxlen=VOTE_WINDOW),   # guantes azules (legacy)
                'G':  deque(maxlen=VOTE_WINDOW),   # cualquier guante detectado
                'BK': deque(maxlen=VOTE_WINDOW),   # camiseta negra
            }

    def update(self, pid, w_ok, r_ok, b_ok, has_glove=False, black_shirt=False):
        if self.locked: return
        self._ensure(pid); d = self._wins[pid]
        d['W'].append(w_ok); d['R'].append(r_ok); d['B'].append(b_ok)
        d['G'].append(has_glove); d['BK'].append(black_shirt)

    def try_confirm(self):
        if self.locked: return False
        if self.mode != "none": return False

        bk_thresh = max(8, VOTE_NEEDED // 2)

        # ── SESIÓN NORMAL (prioridad): 2 personas con guantes + 1 camiseta negra ──
        gloved = [(pid, d) for pid, d in self._wins.items()
                  if sum(d['G']) >= VOTE_NEEDED]
        if len(gloved) >= 2:
            bk_pid = None
            for pid, d in gloved:
                if sum(d['BK']) >= bk_thresh:
                    bk_pid = pid; break
            if bk_pid is not None:
                other = [p for p, _ in gloved if p != bk_pid][0]
                self.red_pid = bk_pid; self.blue_pid = other
                self.mode = "fight"; self.locked = True
                return False

        # ── MODO PRUEBA: 1 persona con guantes blancos + torso descubierto ──
        if len(gloved) <= 1:
            for pid, d in self._wins.items():
                if sum(d['W']) >= VOTE_NEEDED:
                    self.test_pid = pid; self.mode = "test"; return True

        return False

    def clear(self):
        self._wins.clear(); self.locked = False
        self.test_pid = self.red_pid = self.blue_pid = None; self.mode = "none"

    def force_test(self, pid): self.clear(); self.test_pid=pid; self.mode="test"; self.locked=True
    def force_red(self, pid):
        self.red_pid=pid; self.mode="fight"
        if self.blue_pid: self.locked=True
    def force_blue(self, pid):
        self.blue_pid=pid; self.mode="fight"
        if self.red_pid: self.locked=True

    @property
    def ready(self):
        return (self.mode=="test" or
                (self.mode=="fight" and self.red_pid is not None and self.blue_pid is not None))

# ══════════════════════════════════════════════════════════════════
#  [2] HUNGARIAN MULTI-CAMERA MATCHING
# ══════════════════════════════════════════════════════════════════
def _torso_2d(kp):
    pts = [kp[i] for i in [5,6,11,12] if i < len(kp) and kp[i][0]>0 and kp[i][1]>0]
    if not pts: return None
    return np.mean(pts, axis=0)

def _bbox(kp):
    pts = [(kp[i][0], kp[i][1]) for i in range(len(kp)) if kp[i][0]>0 and kp[i][1]>0]
    if not pts: return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))

def _iou(b1, b2):
    if b1 is None or b2 is None: return 0.0
    ix0=max(b1[0],b2[0]); iy0=max(b1[1],b2[1])
    ix1=min(b1[2],b2[2]); iy1=min(b1[3],b2[3])
    iw=max(0,ix1-ix0); ih=max(0,iy1-iy0); inter=iw*ih
    a1=(b1[2]-b1[0])*(b1[3]-b1[1]); a2=(b2[2]-b2[0])*(b2[3]-b2[1])
    union=a1+a2-inter
    return inter/union if union>0 else 0.0

def hungarian_match(persons_a, persons_sec, max_dist=300.0):
    """
    Match persons from cam_a to persons_sec using Hungarian algorithm.
    Cost = 0.6 * torso_distance + 0.4 * (1 - bbox_IOU).
    Returns list of (idx_a, idx_sec) matched pairs.
    """
    if not persons_a or not persons_sec: return []
    na = len(persons_a); nb = len(persons_sec)
    cost = np.full((na, nb), fill_value=max_dist * 2.0, dtype=np.float64)
    for i, (_, kp_a, _, _) in enumerate(persons_a):
        tc_a = _torso_2d(kp_a); bb_a = _bbox(kp_a)
        for j, (_, kp_b, _, _) in enumerate(persons_sec):
            tc_b = _torso_2d(kp_b); bb_b = _bbox(kp_b)
            dist = max_dist
            if tc_a is not None and tc_b is not None:
                dist = float(np.linalg.norm(tc_a - tc_b))
            if dist > max_dist: continue
            iou = _iou(bb_a, bb_b)
            cost[i, j] = 0.6 * dist + 0.4 * (1.0 - iou) * max_dist
    if _HAS_SCIPY:
        row_ind, col_ind = linear_sum_assignment(cost)
        matches = [(r, c) for r, c in zip(row_ind, col_ind) if cost[r, c] < max_dist]
    else:
        # Greedy fallback
        matches = []
        used = set()
        for i in range(na):
            best_j, best_c = -1, max_dist
            for j in range(nb):
                if j not in used and cost[i, j] < best_c:
                    best_j, best_c = j, cost[i, j]
            if best_j >= 0:
                matches.append((i, best_j)); used.add(best_j)
    return matches

# ══════════════════════════════════════════════════════════════════
#  VISION ENGINE v4
# ══════════════════════════════════════════════════════════════════
class VisionEngine(threading.Thread):
    def __init__(self, cam_a_idx, cam_b_idx, cam_c_idx, baseline_m):
        super().__init__(daemon=True)
        self.cam_a_idx = cam_a_idx
        self.cam_b_idx = cam_b_idx
        self.cam_c_idx = cam_c_idx
        # Explicit camera map — logged on startup to diagnose camera assignment bugs
        self.camera_map = {
            "A": cam_a_idx,
            "B": cam_b_idx,
            "C": cam_c_idx,
        }
        print(f"[CAM MAP] {self.camera_map}")
        self.stereo_ab = StereoFuser(baseline_m=baseline_m)
        self.stereo_ac = StereoFuser(baseline_m=baseline_m*1.2)
        self.roles = RoleDetector()
        self.red   = Fighter("ROJA", RED)
        self.blue  = Fighter("AZUL", BLU)
        self.session_state = "IDLE"; self.phase = "IDLE"
        self.rnd = 1; self.rnd_done = 0
        self.t_start = self.t_pause = self.t_paused = 0.0
        self.rnd_stats = {}; self.rnd_winners = {}; self.opp_pos3d = {}
        self._ts = self._fresh_ts(); self._ts_t0 = 0.0
        self._go = True; self._lock = threading.Lock()
        self._solo_frames = 0   # consecutive IDLE frames with exactly 1 person → auto test-mode
        self._frame_a = self._frame_b = self._frame_c = None
        self._stats = {}; self._pids = []
        self._status_msg = "Muestra guantes + torso  |  asigna roles"
        # Glove detection tracking per person (pid → bool)
        self._glove_votes: dict = {}    # pid → deque of bool votes
        self._glove_ok:    dict = {}    # pid → confirmed has glove
        self._bare_warned  = False      # suppress repeat warnings
        self._log_msgs = deque(maxlen=20)
        self._fps_counter = deque(maxlen=30)
        self._pose_tracker = PoseTracker()
        # [10] Telemetry
        self._telem = {
            'lat_a_ms': 0.0, 'lat_b_ms': 0.0, 'lat_c_ms': 0.0,
            'total_infers': 0, 'valid_stereo': 0, 'kp_per_frame': 0,
            'api_sent': 0, 'api_err': 0,
        }

    def _fresh_ts(self):
        return {'fp':0,'dv':0,'pd':0,'hd':0,
                'ss':deque(maxlen=500),'es':deque(maxlen=500),
                'cc':{"JAB":0,"CROSS":0,"HOOK":0,"UPPERCUT":0,"OVERHAND":0,"BODYSHOT":0,"UNKNOWN":0}}

    def _reset_ts(self): self._ts = self._fresh_ts(); self._ts_t0 = time.time()

    @property
    def tm(self): return self.roles.mode == "test"

    def _score(self, f):
        if self.tm:
            # TEST mode: puntaje basado en golpes (boxeo completo)
            if f.strikes == 0: return 0.0
            return f.connected/max(1,f.strikes)*100 + f.aggr*0.2 + f.max_spd_ms*2
        else:
            # FIGHT mode: agresividad + evasión (sin conteo de golpes)
            aggr_sc = min(f.aggr * 0.6 + f.max_spd_ms * 1.5, 60.0)
            evad_sc = min(f.head.dodges * 3.5 + f.head.agility() * 0.4, 40.0)
            return round(aggr_sc + evad_sc, 1)

    def _check_hit(self, wp3, pid):
        hb = hf = hbody = False
        rp = self.roles.red_pid; bp = self.roles.blue_pid
        opp = bp if pid==rp else (rp if pid==bp else None)
        if opp and opp in self.opp_pos3d:
            hb = dist3d(wp3, self.opp_pos3d[opp]) < HIT_R_M
        oh = (self.blue.head.last_pos3d if pid==rp else self.red.head.last_pos3d)
        if oh: hf = dist3d(wp3, oh) < HEAD_HIT_R_M
        # body hit: check hip center of opponent
        opp_ftr = self.blue if pid==rp else self.red
        hip3 = hip_center_3d(opp_ftr.pts3d)
        if hip3: hbody = dist3d(wp3, hip3) < BODY_HIT_R_M
        return hb, hf, hbody

    @staticmethod
    def _parse_result(res):
        out = []
        if res is None: return out
        try:
            kps_xy   = res[0].keypoints.xy.cpu().numpy()
            kps_conf = res[0].keypoints.conf
            kps_conf = (kps_conf.cpu().numpy() if kps_conf is not None
                        else np.ones((len(kps_xy),17), np.float32)*0.5)
            for kp, cf in zip(kps_xy, kps_conf):
                if kp is None or len(kp) < 11: continue
                out.append((kp, cf))
        except: pass
        return out

    def _process_cam_kp(self, frame, kp_list, cf_list, pid_offset=0):
        persons = []; fh, fw = frame.shape[:2]
        for idx, (kp, cf) in enumerate(zip(kp_list, cf_list)):
            lw=kp[9]; rw=kp[10]
            lx,ly=float(lw[0]),float(lw[1]); rx,ry=float(rw[0]),float(rw[1])
            lv = not(lx==0 and ly==0) and 0<=lx<fw and 0<=ly<fh
            rv = not(rx==0 and ry==0) and 0<=rx<fw and 0<=ry<fh
            if not lv and not rv: continue
            cL = classify_glove(frame, int(lx), int(ly)) if lv else {}
            cR = classify_glove(frame, int(rx), int(ry)) if rv else {}
            bare_l = detect_bare_hand(frame, int(lx), int(ly)) if lv else False
            bare_r = detect_bare_hand(frame, int(rx), int(ry)) if rv else False
            any_glove = (cL.get('white',False) or cL.get('red',False) or cL.get('blue',False)
                         or cR.get('white',False) or cR.get('red',False) or cR.get('blue',False))
            _bt = bare_torso(frame, kp)
            gi = {'white': cL.get('white',False) or cR.get('white',False),
                  'red':   cL.get('red',  False) or cR.get('red',  False),
                  'blue':  cL.get('blue', False) or cR.get('blue', False),
                  'bare':  _bt,
                  'bare_hands': (bare_l or bare_r) and not any_glove,
                  'has_glove':  any_glove,
                  'black_shirt': (not _bt) and detect_black_shirt(frame, kp)}
            persons.append((idx+pid_offset, kp, cf, gi))
        return persons

    def _process_cam(self, frame, res, pid_offset=0):
        parsed = self._parse_result(res)
        kps = [kp for kp, _ in parsed]; cfs = [cf for _, cf in parsed]
        return self._process_cam_kp(frame, kps, cfs, pid_offset)

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock: self._log_msgs.append(f"[{ts}] {msg}")

    def _build_fighter_stat_dict(self, ftr: 'Fighter') -> dict:
        """Build a complete stats dict for one fighter (used in reports)."""
        return {
            "strikes":       ftr.strikes,
            "connected":     ftr.connected,
            "accuracy_pct":  ftr.accuracy(),
            "face_hits":     ftr.face_hits,
            "body_hits":     ftr.body_hits,
            "max_speed_ms":  round(ftr.max_spd_ms, 2),
            "max_ext_m":     round(ftr.max_ext_m, 3),
            "dodges":        ftr.head.dodges,
            "agility":       round(ftr.head.agility(), 1),
            "aggression":    ftr.aggr,
            "power_strikes": ftr.power_strikes,
            "combo_count":   ftr.combo_count,
            "stance":        ftr.stance,
            "punch_types":       ftr.ptypes.copy(),
            "punch_balance":     ftr.punch_balance(),
            "kinetic_chain_avg": ftr.kinetic_chain_avg(),
            "punch_left_count":  ftr.punch_left_count,
            "punch_right_count": ftr.punch_right_count,
        }

    def _end_round(self):
        t_round_end = datetime.datetime.now().isoformat()
        if self.tm:
            # ── TEST MODE ─────────────────────────────────────────
            acc = self.red.connected / max(1, self.red.strikes) * 100
            sc  = self._score(self.red)
            r_stats = self._build_fighter_stat_dict(self.red)
            r_boxing = BoxingScorer.compute(r_stats)
            self.rnd_stats[self.rnd] = {
                "mode": "test",
                "timestamp": t_round_end,
                "strikes": self.red.strikes,
                "connected": self.red.connected,
                "max_speed_ms": self.red.max_spd_ms,
                "max_ext_m": self.red.max_ext_m,
                "score": sc,
                "punch_types": self.red.ptypes.copy(),
                "accuracy": round(acc, 1),
                "power_strikes": self.red.power_strikes,
                "combo_count": self.red.combo_count,
                "stance": self.red.stance,
                "boxing_score": r_boxing,
            }
            self.rnd_winners[self.rnd] = "test"
            self._reset_ts()
            self._log(f"Round {self.rnd}: TEST — {self.red.strikes} golpes, {acc:.1f}%  "
                      f"Poder:{self.red.power_strikes} Combos:{self.red.combo_count}")
            self._emit_round_report(self.rnd, "test", self.rnd_stats[self.rnd], t_round_end)
        else:
            # ── FIGHT MODE: Agresividad + Evasión (sin conteo de golpes) ──────────
            r_stats = self._build_fighter_stat_dict(self.red)
            b_stats = self._build_fighter_stat_dict(self.blue)
            r_sc = AggressivenessScorer.compute(r_stats)
            b_sc = AggressivenessScorer.compute(b_stats)
            pts_r, pts_b = AggressivenessScorer.ten_must(r_sc['raw_score'], b_sc['raw_score'])

            if pts_r > pts_b:   w = "red"
            elif pts_b > pts_r: w = "blue"
            else:               w = "draw"

            self.rnd_winners[self.rnd] = w
            self.rnd_stats[self.rnd] = {
                "winner":     w,
                "timestamp":  t_round_end,
                "scoring":    "aggressiveness+evasion",
                "scorecard":  {"red": pts_r, "blue": pts_b},
                "red_score":  r_sc['raw_score'],
                "blue_score": b_sc['raw_score'],
                "red":   {**r_stats, "boxing_score": r_sc, "round_pts": pts_r},
                "blue":  {**b_stats, "boxing_score": b_sc, "round_pts": pts_b},
            }
            card_txt = AggressivenessScorer.generate_scorecard_text(
                self.rnd, r_stats, b_stats, r_sc, b_sc, pts_r, pts_b)
            print(card_txt)
            self._log(f"Round {self.rnd}: {w.upper()} ({pts_r}-{pts_b})  "
                      f"Agres R:{self.red.aggr} B:{self.blue.aggr}  "
                      f"Esqv R:{self.red.head.dodges} B:{self.blue.head.dodges}")
            self._emit_round_report(self.rnd, "fight", self.rnd_stats[self.rnd], t_round_end)

    def _emit_round_report(self, rnd: int, mode: str, data: dict, ts: str):
        """
        Save a per-round JSON report to disk and log a compact summary.
        File: round_report_<YYYYMMDD_HHMMSS>_R<N>.json
        """
        try:
            fname = f"round_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_R{rnd}.json"
            report = {
                "version":   "1.0",
                "system":    BUILD_VERSION,
                "round":     rnd,
                "mode":      mode,
                "timestamp": ts,
                "data":      data or self.rnd_stats.get(rnd, {}),
                "session_summary": {
                    "rounds_completed": self.rnd_done + 1,
                    "total_rounds":     TOTAL_ROUNDS,
                    "round_winners":    {str(k): v for k, v in self.rnd_winners.items()},
                },
            }
            with open(fname, 'w', encoding='utf-8') as fp:
                json.dump(report, fp, indent=2, ensure_ascii=False)
            self._log(f"Reporte Round {rnd} → {fname}")
        except Exception as e:
            print(f"[report] Error guardando round report: {e}")

    def _emit_session_report(self):
        """
        Aggregate all round data into a final session JSON report with qualification grade.
        Prints a CompuBox-style final scoreboard and saves session_report_<ts>.json.
        """
        try:
            ts        = datetime.datetime.now()
            ts_str    = ts.isoformat()
            is_test   = self.tm

            red_raw_scores: list  = []
            blue_raw_scores: list = []
            red_wins = blue_wins = draws = n_played = 0

            for r in range(1, TOTAL_ROUNDS + 1):
                rdata = self.rnd_stats.get(r, {})
                mode  = rdata.get('mode', '')
                if mode == 'skipped':
                    continue
                n_played += 1
                if mode == 'test':
                    bx = rdata.get('boxing_score', {})
                    red_raw_scores.append(bx.get('raw_score', 0.0))
                else:  # fight
                    red_raw_scores.append(rdata.get('red_score', 0.0))
                    blue_raw_scores.append(rdata.get('blue_score', 0.0))
                    w = rdata.get('winner', '')
                    if   w == 'red':  red_wins  += 1
                    elif w == 'blue': blue_wins += 1
                    elif w == 'draw': draws     += 1

            if is_test:
                q_red  = BoxingScorer.compute_qualification(red_raw_scores)
                q_blue = None
            else:
                # FIGHT mode: scores ya están en rango 0-100 (AggressivenessScorer)
                q_red  = AggressivenessScorer.compute_qualification(red_raw_scores)
                q_blue = AggressivenessScorer.compute_qualification(blue_raw_scores)

            if is_test:
                final_summary = {
                    'mode':           'test',
                    'rounds_played':  n_played,
                    'qualification':  q_red,
                }
                summary_txt = (
                    f"\n{'═'*62}\n"
                    f"  REPORTE FINAL DE SESIÓN  —  MODO TEST\n"
                    f"{'─'*62}\n"
                    f"  Rounds completados  : {n_played} / {TOTAL_ROUNDS}\n"
                    f"  Score promedio      : {q_red['avg_raw']:.1f} pts (raw)\n"
                    f"  Score normalizado   : {q_red['score']:.1f} / 100\n"
                    f"  ★  CALIFICACIÓN     : {q_red['grade']}  —  {q_red['label']}\n"
                    f"{'═'*62}\n"
                )
            else:
                if   red_wins  > blue_wins: overall_winner = "ROJO"
                elif blue_wins > red_wins:  overall_winner = "AZUL"
                else:                       overall_winner = "EMPATE"
                final_summary = {
                    'mode':               'fight',
                    'rounds_played':      n_played,
                    'red_wins':           red_wins,
                    'blue_wins':          blue_wins,
                    'draws':              draws,
                    'overall_winner':     overall_winner,
                    'red_qualification':  q_red,
                    'blue_qualification': q_blue,
                }
                summary_txt = (
                    f"\n{'═'*62}\n"
                    f"  REPORTE FINAL DE SESIÓN  —  MODO PELEA\n"
                    f"{'─'*62}\n"
                    f"  Rounds completados  : {n_played} / {TOTAL_ROUNDS}\n"
                    f"  ROJO {red_wins}V – AZUL {blue_wins}V – {draws} EMPATES\n"
                    f"  ★  GANADOR SESIÓN   : {overall_winner}\n"
                    f"{'─'*62}\n"
                    f"  ROJO — Cal: {q_red['grade']}  {q_red['score']:.1f}/100  {q_red['label']}\n"
                    f"  AZUL — Cal: {q_blue['grade']}  {q_blue['score']:.1f}/100  {q_blue['label']}\n"
                    f"{'═'*62}\n"
                )

            print(summary_txt)
            grade_log = q_red['grade']
            self._log(f"★ SESIÓN FINAL: Cal={grade_log} ({q_red['score']:.0f}/100) — {q_red['label']}")

            report = {
                'version':       '1.0',
                'system':        BUILD_VERSION,
                'generated_at':  ts_str,
                'total_rounds':  TOTAL_ROUNDS,
                'rounds_played': n_played,
                'rounds': {
                    str(r): self.rnd_stats.get(r, {'mode': 'skipped'})
                    for r in range(1, TOTAL_ROUNDS + 1)
                },
                'summary': final_summary,
            }
            fname = f"session_report_{ts.strftime('%Y%m%d_%H%M%S')}.json"
            with open(fname, 'w', encoding='utf-8') as fp:
                json.dump(report, fp, indent=2, ensure_ascii=False)
            self._log(f"Reporte sesión → {fname}")
        except Exception as e:
            print(f"[session_report] Error: {e}")

    def _check_gloves_ready(self) -> tuple:
        """
        Returns (ok: bool, msg: str).
        In FIGHT mode: both fighters must have confirmed gloves.
        In TEST mode: allowed with or without gloves (training).
        """
        mode = self.roles.mode
        if mode == "test":
            return True, "TEST MODE – sin requisito de guantes"
        if mode != "fight":
            return False, "Asigna roles primero (ROJO + AZUL)"
        rp = self.roles.red_pid; bp = self.roles.blue_pid
        r_ok = self._glove_ok.get(rp, False)
        b_ok = self._glove_ok.get(bp, False)
        if r_ok and b_ok:
            return True, "Guantes detectados en ambos peleadores ✓"
        missing = []
        if not r_ok: missing.append("ROJO sin guantes")
        if not b_ok: missing.append("AZUL sin guantes")
        return False, " | ".join(missing) + " — usa guantes para iniciar"

    def cmd_start(self):
        if not self.roles.ready: return False
        gloves_ok, glove_msg = self._check_gloves_ready()
        if not gloves_ok:
            self._log(f"⚠ INICIO BLOQUEADO: {glove_msg}")
            self._status_msg = glove_msg
            return False
        self.session_state="RUNNING"; self.phase="ROUND"
        self.rnd=1; self.rnd_done=0
        self.t_start=time.time(); self.t_paused=0.0; self.t_pause=0.0
        self.red.reset(); self.blue.reset()
        self.rnd_stats={}; self.rnd_winners={}; self._reset_ts()
        if DATASET_ENABLED: DATASET.start_session()
        # The WEB is the owner of fight_id — the motor never invents one locally.
        # If no official session is ready, try to fetch the active fight from the web.
        if not (FAPI._fight_id and FAPI._session_id):
            self._log("Sin sesión oficial — buscando sesión activa en la web…")
            FAPI.fetch_active_session()

        if FAPI._fight_id:
            _fight_uuid = FAPI._fight_id
            red_name    = FAPI._fighter_red_name or "Esquina Roja"
            blue_name   = FAPI._fighter_blue_name or "Esquina Azul"
            self._log(f"=== SESIÓN: {red_name} vs {blue_name} ===")
        else:
            # No fight_id from web — refuse to start to avoid FK / desync errors
            self._log("❌ INICIO BLOQUEADO: la web no tiene sesión activa. "
                      "Crea la pelea en fighter-id.org primero.")
            self.session_state = "IDLE"
            return False

        FAPI.start_session(
            fight_id       = _fight_uuid,
            fighter_a_name = red_name,
            fighter_b_name = blue_name,
            mode           = "fight" if not self.tm else "test",
        )
        return True

    def cmd_start_test(self):
        """
        Test rápido: asigna automáticamente el primer peleador detectado,
        omite chequeo de guantes y arranca la sesión de inmediato.
        Ideal para entrenamiento individual — no requiere sesión activa en Supabase.
        """
        # Auto-asignar primer PID visible como TEST
        if self._pids:
            self.roles.force_test(self._pids[0])
        else:
            # Sin persona visible todavía — igualmente forzar modo TEST
            self.roles.clear()
            self.roles.mode   = "test"
            self.roles.locked = True
        self.session_state="RUNNING"; self.phase="ROUND"
        self.rnd=1; self.rnd_done=0
        self.t_start=time.time(); self.t_paused=0.0; self.t_pause=0.0
        self.red.reset(); self.blue.reset()
        self.rnd_stats={}; self.rnd_winners={}; self._reset_ts()
        if DATASET_ENABLED: DATASET.start_session()
        self._log("=== TEST RÁPIDO INICIADO (1 peleador) ===")
        FAPI.start_session_test()
        return True

    def cmd_pause(self):
        if self.session_state=="RUNNING":
            self.session_state="PAUSED"; self.t_pause=time.time(); self._log("Pausa")
        elif self.session_state=="PAUSED":
            self.t_paused += time.time()-self.t_pause
            self.session_state="RUNNING"; self._log("Resume")

    def cmd_end_round(self):
        if self.session_state not in ("RUNNING","PAUSED") or self.phase != "ROUND":
            return
        self._end_round()
        self.rnd_done += 1
        if self.rnd_done >= TOTAL_ROUNDS:
            # Última ronda: cerrar sesión
            self._log("=== SESIÓN TERMINADA ===")
            self._emit_session_report()
            if DATASET_ENABLED: DATASET.stop_session()
            self.session_state = "IDLE"; self.phase = "IDLE"
        else:
            # Transición a descanso — impide que el auto-advance dispare _end_round() de nuevo
            self.phase = "REST"
            self.t_start = time.time(); self.t_paused = 0.0
            self.session_state = "RUNNING"
            self._log(f"Round {self.rnd} finalizado — descanso ({REST_TIME}s)")

    def cmd_end_session(self):
        """Terminate session early and emit reports for ALL rounds (played + skipped)."""
        if self.session_state not in ("RUNNING", "PAUSED"):
            return
        # End current round only if it had meaningful activity
        if self.phase == "ROUND":
            has_activity = (self.red.aggr > 0 or self.red.strikes > 0
                            or self.blue.aggr > 0 or self.blue.strikes > 0)
            if has_activity:
                self._end_round()
                self.rnd_done += 1
            else:
                self._log(f"Round {self.rnd} descartado (sin actividad registrada)")
                self.phase = "IDLE"
        # Emit skipped-round reports for rounds not yet played
        ts_now = datetime.datetime.now().isoformat()
        self.red.reset(); self.blue.reset()   # zero stats so skipped reports are clean
        for r in range(self.rnd_done + 1, TOTAL_ROUNDS + 1):
            skipped_data = {
                "mode": "skipped",
                "red":  self._build_fighter_stat_dict(self.red),
                "blue": self._build_fighter_stat_dict(self.blue),
            }
            self.rnd_stats[r]   = skipped_data
            self.rnd_winners[r] = "skipped"
            self._emit_round_report(r, "skipped", skipped_data, ts_now)
        if DATASET_ENABLED:
            DATASET.stop_session()
        self._emit_session_report()
        _red_wins  = sum(1 for v in self.rnd_winners.values() if v == "red")
        _blue_wins = sum(1 for v in self.rnd_winners.values() if v == "blue")
        if _red_wins > _blue_wins:   _winner = "red"
        elif _blue_wins > _red_wins: _winner = "blue"
        else:                        _winner = "draw"
        FAPI.end_fight(
            winner        = _winner,
            round_results = {str(k): v for k, v in self.rnd_winners.items()},
            red_stats     = self._build_fighter_stat_dict(self.red),
            blue_stats    = self._build_fighter_stat_dict(self.blue),
        )
        self.session_state = "IDLE"; self.phase = "IDLE"
        self._log("=== SESIÓN FINALIZADA (todos los reportes emitidos) ===")

    def cmd_force_test(self, pid=None):
        p = pid if pid is not None else (self._pids[0] if self._pids else 0)
        self.roles.force_test(p); self._log(f"Rol TEST → pid {p}")

    def cmd_force_red(self, pid=None):
        p = pid if pid is not None else (self._pids[0] if self._pids else 0)
        if not self.roles.locked: self.roles.force_red(p); self._log(f"Rol ROJO → pid {p}")

    def cmd_force_blue(self, pid=None):
        p = pid if pid is not None else (self._pids[1] if len(self._pids)>1 else (self._pids[0] if self._pids else 1))
        if not self.roles.locked: self.roles.force_blue(p); self._log(f"Rol AZUL → pid {p}")

    def cmd_clear(self): self.roles.clear(); self._log("Roles limpiados")
    def cmd_stop(self):  self._go = False

    def get_frames(self):
        with self._lock: return self._frame_a, self._frame_b, self._frame_c

    def get_stats(self):
        with self._lock: return dict(self._stats)

    def get_logs(self):
        with self._lock: return list(self._log_msgs)

    def get_round_stats(self) -> dict:
        """Retorna copia de rnd_stats para el LiveStreamManager (thread-safe vía GIL)."""
        return dict(self.rnd_stats)

    def run(self):
        def open_cap(idx, fps=30):
            """
            Open camera at target resolution + fps.

            Windows-specific notes:
            - MSMF uses its own camera index mapping that can differ from
              DirectShow.  'VideoCapture(1, MSMF)' may silently open cam 0
              again.  We try DSHOW first — its indices match the OS/probe.
            - Razer Kiyo X requires FOURCC=MJPG to reach 60fps at 1080p.
              YUYV/raw saturates USB bandwidth and caps at 30fps.
            - Property order: FOURCC → WIDTH → HEIGHT → FPS → BUFFERSIZE.
            - After changing resolution the camera buffers stale frames;
              flush with reads + sleep before returning.
            """
            # DSHOW first: consistent index mapping on Windows for USB webcams
            # MSMF second: good for some built-ins
            # CAP_ANY last: let OpenCV auto-select as last resort
            backends = (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY)
            for backend in backends:
                cap = None
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened():
                        cap.release(); continue
                    # Initial warmup — some cameras deliver black frames on first read
                    for _ in range(3): cap.read()
                    time.sleep(0.10)
                    # MJPEG required for 60fps at 1080p on USB webcams
                    if fps >= 60:
                        cap.set(cv2.CAP_PROP_FOURCC,
                                cv2.VideoWriter_fourcc(*'MJPG'))
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
                    cap.set(cv2.CAP_PROP_FPS, fps)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    # Flush stale frames after resolution change
                    for _ in range(5): cap.read()
                    time.sleep(0.12)
                    a_fps = cap.get(cv2.CAP_PROP_FPS)
                    a_w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    a_h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    # Sanity check: MSMF sometimes opens wrong camera
                    # If we wanted 60fps but got 30, and backend is MSMF, reject
                    if fps >= 60 and a_fps < 50 and backend == cv2.CAP_MSMF:
                        print(f"  [open_cap] idx={idx} bk=MSMF devolvió {a_fps:.0f}fps "
                              f"(req {fps}) — posible índice incorrecto, probando DSHOW")
                        cap.release(); continue
                    bk_name = {cv2.CAP_DSHOW:'DSHOW', cv2.CAP_MSMF:'MSMF',
                               cv2.CAP_ANY:'ANY'}.get(backend, str(backend))
                    print(f"  [open_cap] idx={idx} bk={bk_name} "
                          f"→ {a_w}x{a_h}@{a_fps:.0f}fps (req {fps}fps)")
                    return cap
                except Exception as e:
                    print(f"  [open_cap] idx={idx} backend={backend}: {e}")
                    if cap:
                        try: cap.release()
                        except: pass
            # Last-resort: bare VideoCapture (no resolution/fps guarantees)
            print(f"  [open_cap] idx={idx} — todos los backends fallaron, "
                  f"abriendo sin config (resolución nativa)")
            cap = cv2.VideoCapture(idx)
            for _ in range(3): cap.read()
            return cap

        def fps_of(idx, default=30):
            """
            Target FPS for camera at idx, detected by model name.
            Razer Kiyo X: 1080p@60fps (MJPEG).
            Logitech C920: 1080p@30fps max.
            """
            for c in ALL_CAMERAS:
                if c['index'] != idx: continue
                name = c.get('name', '').lower()
                if 'razer' in name or 'kiyo' in name:
                    return 60
                if 'c920' in name or 'logitech' in name:
                    return 30
                probe_fps = c.get('fps', default)
                return 60 if probe_fps >= 55 else int(probe_fps) if probe_fps > 0 else default
            return default

        print(f"[VisionEngine] iniciando A={self.cam_a_idx} B={self.cam_b_idx} C={self.cam_c_idx}")
        self._log(f"Cargando YOLO pose (device={_DEVICE})...")
        model_a = YOLO("yolov8n-pose.pt")
        model_b = YOLO("yolov8n-pose.pt")
        model_c = YOLO("yolov8n-pose.pt")
        # Move models to GPU — DML (AMD/Intel) or CUDA (NVIDIA)
        # CRITICAL: _DML_DEV must be applied here; YOLO() defaults to CPU
        if _DEVICE == "dml":
            try:
                model_a.to(_DML_DEV); model_b.to(_DML_DEV); model_c.to(_DML_DEV)
                print("[GPU] Modelos YOLO → AMD GPU (DirectML)")
            except Exception as _e_dml:
                print(f"[GPU] DirectML falló al mover modelos: {_e_dml} → usando CPU")
        elif _DEVICE == "cuda":
            model_a.to("cuda"); model_b.to("cuda"); model_c.to("cuda")
            print("[GPU] Modelos YOLO → NVIDIA GPU (CUDA)")

        # [1] THREE independent inference threads — each with its own model
        # to avoid 'Conv has no attribute bn' race condition during first inference
        inf_a = InferThread(model_a, "InferA")
        inf_b = InferThread(model_b, "InferB")
        inf_c = InferThread(model_c, "InferC")
        inf_a.start(); inf_b.start(); inf_c.start()

        cap_a = open_cap(self.cam_a_idx, fps_of(self.cam_a_idx, 60))
        cap_b = (open_cap(self.cam_b_idx, fps_of(self.cam_b_idx, 60))
                 if self.cam_b_idx is not None else None)
        cap_c = (open_cap(self.cam_c_idx, fps_of(self.cam_c_idx, 60))   # Razer soporta 60fps
                 if self.cam_c_idx is not None else None)

        if not cap_a.isOpened():
            self._log(f"ERROR: no se pudo abrir CAM A (idx={self.cam_a_idx})")
            inf_a.stop(); inf_b.stop(); inf_c.stop(); return

        # Readers en background — el main loop no bloquea en cap.read()
        rdr_a = CamReader(cap_a); rdr_a.start()
        rdr_b = CamReader(cap_b) if cap_b else None
        if rdr_b: rdr_b.start()
        rdr_c = CamReader(cap_c) if cap_c else None
        if rdr_c: rdr_c.start()

        # Load calibration if available
        calib = StereoCalibrator.load()
        if calib:
            self.stereo_ab.B  = calib['baseline_m']
            self.stereo_ab.f  = calib['focal_px']
            self.stereo_ab.cx = calib['cx']
            self.stereo_ab.cy = calib['cy']
            self.stereo_ac.B  = calib['baseline_m'] * 1.2
            self.stereo_ac.f  = calib['focal_px']
            self.stereo_ac.cx = calib['cx']
            self.stereo_ac.cy = calib['cy']
            self._log(f"Calibración cargada: BL={calib['baseline_m']:.3f}m RMS={calib.get('rms',0):.4f}")
        else:
            self._log("Sin calibración — usando estimaciones por defecto")

        self._log("Calentando cámaras (1080p necesita ~1.5s)...")
        time.sleep(1.5)  # 1080p USB webcams need time to stabilize after resolution change

        last_a = last_b = last_c = None
        fc = 0
        # Buffer de timestamps para sincronizar CAM C (30fps) con el ciclo de 60fps de A/B.
        # Cada entrada: (timestamp_float, frame_bgr)
        _cam_c_buf: deque = deque(maxlen=CAM_C_TS_BUF)
        use_tracking = False
        _scale  = CAM_W / 640
        GLOVE_R = max(8,  int(8  * _scale))
        HEAD_R  = max(12, int(16 * _scale))

        self._log(f"{BUILD_VERSION} [{BUILD_DATE}] listo ✓  GPU={_DEVICE.upper()}"
                  f"  scipy={'YES' if _HAS_SCIPY else 'NO'}"
                  f"  INFER AB/{INFER_EVERY_AB} C/{INFER_EVERY_C}  RES={CAM_W}x{CAM_H}")

        while self._go:
            ret_a, frame_a = rdr_a.read()
            if not ret_a or frame_a is None:
                _fail = getattr(self, '_cam_a_fail', 0) + 1
                self._cam_a_fail = _fail
                if _fail > 30:
                    self._log(f"CAM A sin frames ({_fail}x) — verifica dispositivo")
                    time.sleep(0.5)
                else:
                    time.sleep(0.02)
                continue
            self._cam_a_fail = 0
            frame_a = cv2.flip(frame_a, 1)
            frame_b = None
            if rdr_b:
                ret_b, fb = rdr_b.read()
                if ret_b and fb is not None: frame_b = cv2.flip(fb, 1)
            # CAM C — 30fps cenital: leer y añadir al buffer con timestamp
            if rdr_c:
                ret_c, fr = rdr_c.read()
                if ret_c and fr is not None:
                    _cam_c_buf.append((time.time(), cv2.flip(fr, 1)))

            fc += 1; ct = time.time()
            self._fps_counter.append(ct)
            gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)

            # Seleccionar el frame de CAM C más cercano en tiempo a este ciclo
            frame_c = None
            if _cam_c_buf:
                frame_c = min(_cam_c_buf, key=lambda x: abs(x[0] - ct))[1]

            # [1] Inferencia por cámara según sus FPS nativos
            #     A/B (60fps) → YOLO cada INFER_EVERY_AB=2 frames (~30fps YOLO)
            #     C  (30fps)  → YOLO cada INFER_EVERY_C=1 frame  (~30fps YOLO)
            if fc % INFER_EVERY_AB == 0:
                inf_a.submit(frame_a)
                if frame_b is not None: inf_b.submit(frame_b)
                use_tracking = False
            else:
                use_tracking = True
            if frame_c is not None and fc % INFER_EVERY_C == 0:
                inf_c.submit(frame_c)

            r_a = inf_a.result()
            r_b = inf_b.result()
            r_c = inf_c.result()
            if r_a is not None: last_a = r_a
            if r_b is not None: last_b = r_b
            if r_c is not None: last_c = r_c

            # Update pose tracker with fresh YOLO result when available
            if r_a is not None:
                parsed = self._parse_result(r_a)
                if parsed:
                    kp_list = [kp for kp, _ in parsed]
                    cf_list = [cf for _, cf in parsed]
                    self._pose_tracker.update_from_yolo(gray_a, kp_list, cf_list)
            # Always apply optical flow to current frame — eliminates 2-3 frame skeleton lag
            current_kp_list, current_cf_list = self._pose_tracker.track(gray_a)

            img_a = frame_a.copy()
            img_b = frame_b.copy() if frame_b is not None else np.zeros((CAM_H,CAM_W,3), np.uint8)
            img_c = frame_c.copy() if frame_c is not None else np.zeros((CAM_H,CAM_W,3), np.uint8)
            skel_col = GRY if use_tracking else WHT
            for kp in current_kp_list:
                draw_skeleton(img_a, kp, color=skel_col)

            if self.tm and self.session_state == "RUNNING":
                self._ts['fp'] += 1

            persons_a = self._process_cam_kp(frame_a, current_kp_list, current_cf_list, 0)

            # [1+2] Independent inference + Hungarian matching for B and C
            persons_b = []
            if frame_b is not None:
                if r_b is not None:
                    # Use actual CAM B inference
                    parsed_b = self._parse_result(r_b)
                    kps_b = [kp for kp, _ in parsed_b]
                    cfs_b = [cf for _, cf in parsed_b]
                    persons_b = self._process_cam_kp(frame_b, kps_b, cfs_b, 100)
                elif last_b is not None:
                    parsed_b = self._parse_result(last_b)
                    kps_b = [kp for kp, _ in parsed_b]
                    cfs_b = [cf for _, cf in parsed_b]
                    persons_b = self._process_cam_kp(frame_b, kps_b, cfs_b, 100)

            persons_c = []
            if frame_c is not None:
                if r_c is not None:
                    parsed_c = self._parse_result(r_c)
                    kps_c = [kp for kp, _ in parsed_c]
                    cfs_c = [cf for _, cf in parsed_c]
                    persons_c = self._process_cam_kp(frame_c, kps_c, cfs_c, 200)
                elif last_c is not None:
                    parsed_c = self._parse_result(last_c)
                    kps_c = [kp for kp, _ in parsed_c]
                    cfs_c = [cf for _, cf in parsed_c]
                    persons_c = self._process_cam_kp(frame_c, kps_c, cfs_c, 200)

            # [2] Hungarian matching
            matches_b = hungarian_match(persons_a, persons_b)
            matches_c = hungarian_match(persons_a, persons_c)
            b_lookup = {ia: persons_b[ib] for ia, ib in matches_b}
            c_lookup = {ia: persons_c[ic] for ia, ic in matches_c}

            # Construir mapa pid_a → kp_c para biomecánica cenital.
            # CAM C es vista CENITAL — NO hace triangulación estéreo con cámaras laterales
            # (ejes de proyección ortogonales). Su rol es entregar datos de rotación/footwork.
            overhead_kp_by_pid: dict = {}
            if persons_c:
                # Asignar personas de CAM C a personas de CAM A por orden de posición X
                # (ambas vistas deberían ver al mismo número de peleadores)
                sorted_a = sorted(enumerate(persons_a),
                                  key=lambda x: float(x[1][1][0][0]) if len(x[1][1])>0 else 0)
                sorted_c = sorted(enumerate(persons_c),
                                  key=lambda x: float(x[1][1][0][0]) if len(x[1][1])>0 else 0)
                for (ia, pa), (_, pc) in zip(sorted_a, sorted_c):
                    overhead_kp_by_pid[pa[0]] = pc[1]  # pid_a → kp_c

            fused_data = {}; n_3d = n_total = 0
            for i_a, (pid_a, kp_a, cf_a, gi_a) in enumerate(persons_a):
                match_b_entry = b_lookup.get(i_a)
                # CAM B (lateral) → triangulación estéreo A+B correcta
                if match_b_entry:
                    _, kp_b, cf_b, _ = match_b_entry
                    fused_kp, pts3d, origin = self.stereo_ab.fuse_keypoints(kp_a, kp_b, cf_a, cf_b)
                    n_3d += sum(1 for o in origin.values() if o=='AB')
                else:
                    pts3d  = {i: self.stereo_ab.depth_from_single(kp_a[i][0],kp_a[i][1])
                              for i in range(min(17,len(kp_a)))
                              if not(kp_a[i][0]==0 and kp_a[i][1]==0)}
                    fused_kp = kp_a; origin = {i:'A' for i in pts3d}

                # CAM C (cenital) → biomecánica overhead, NO profundidad
                overhead_bio = {}
                kp_c_top = overhead_kp_by_pid.get(pid_a)
                if kp_c_top is not None:
                    overhead_bio = extract_overhead_biomechanics(kp_c_top)
                    if overhead_bio.get('valid'):
                        # Marcar keypoints donde la vista cenital aportó rotación
                        for ki in [5, 6, 11, 12, 15, 16]:
                            if ki in origin and origin[ki] != 'ABC':
                                origin[ki] = origin[ki] + 'C'

                fused_data[pid_a] = {'fused_kp': fused_kp, 'pts3d': pts3d,
                                     'origin': origin, 'overhead_bio': overhead_bio}
                n_total += len(origin)

            new_pos3d = {}
            for pid, fd in fused_data.items():
                tc3 = torso_center_3d(fd['pts3d'])
                if tc3: new_pos3d[pid] = tc3
            if new_pos3d: self.opp_pos3d = new_pos3d

            self._pids = [pid for pid,_,_,_ in persons_a]

            # Contador de frames solo — reservado para diagnóstico, ya no dispara auto-test.
            # El modo prueba se activa ahora por el sistema de votos:
            #   → 1 persona + guantes BLANCOS + torso descubierto → MODO PRUEBA
            if len(self._pids) == 1 and self.roles.mode == "none":
                self._solo_frames += 1
            else:
                self._solo_frames = 0

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                bare = gi_a.get('bare', False)
                self.roles.update(pid_a,
                    w_ok=gi_a.get('white',False) and bare,
                    r_ok=gi_a.get('red',  False) and bare,
                    b_ok=gi_a.get('blue', False) and bare,
                    has_glove=gi_a.get('has_glove', False),
                    black_shirt=gi_a.get('black_shirt', False))
                # ── Glove vote tracking (30-frame window) ─────────
                has_g = gi_a.get('has_glove', False)
                if pid_a not in self._glove_votes:
                    self._glove_votes[pid_a] = deque(maxlen=30)
                self._glove_votes[pid_a].append(has_g)
                votes = self._glove_votes[pid_a]
                self._glove_ok[pid_a] = sum(votes) >= max(8, len(votes) // 2)
            self.roles.try_confirm()

            # ── Status message ─────────────────────────────────────
            if self.roles.mode == "test":
                self._status_msg = "MODO PRUEBA — Guantes blancos + sin camiseta — Presiona INICIAR"
            elif self.roles.mode == "fight" and self.roles.red_pid and self.roles.blue_pid:
                self._status_msg = "✓ 2 peleadores + camiseta negra detectados — Presiona INICIAR"
            else:
                n_pids = len(self._pids)
                if n_pids >= 2:
                    self._status_msg = "2 personas detectadas — pon guantes y camiseta negra para iniciar sesión"
                elif n_pids == 1:
                    self._status_msg = "1 persona — guantes BLANCOS + sin camiseta → modo prueba"
                else:
                    self._status_msg = "Esperando peleadores… (guantes box + camiseta negra = sesión | guantes blancos + sin camiseta = prueba)"

            can_det = self.session_state=="RUNNING" and self.phase=="ROUND"
            rp=self.roles.red_pid; bp=self.roles.blue_pid; tp=self.roles.test_pid

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                fd       = fused_data.get(pid_a, {})
                pts3d    = fd.get('pts3d', {})
                origin   = fd.get('origin', {})
                fused_kp = fd.get('fused_kp', kp_a)
                # overhead_bio disponible en fd['overhead_bio'] — ya asignado en ftr.overhead_bio
                ftr = None; rcol = GRY; rlbl = "?"
                if pid_a == rp:   ftr=self.red;  rcol=RED; rlbl="RED"
                elif pid_a == bp: ftr=self.blue; rcol=BLU; rlbl="BLU"
                elif pid_a == tp: ftr=self.red;  rcol=WHT; rlbl="TEST"

                # Pass 3D keypoints + overhead biomechanics to fighter
                if ftr:
                    ftr.pts3d = pts3d
                    ob = fd.get('overhead_bio', {})
                    if ob.get('valid'): ftr.overhead_bio = ob

                nose_p3  = pts3d.get(0)
                nose_2d  = fused_kp[0] if len(fused_kp)>0 and fused_kp[0][0]>0 else None
                if ftr and nose_p3 and nose_2d is not None:
                    ftr.head.update(nose_p3, (int(nose_2d[0]),int(nose_2d[1])), ct)
                    for i in range(3, 0, -1):
                        cv2.circle(img_a, (int(nose_2d[0]),int(nose_2d[1])), HEAD_R+i*2, rcol, 1)
                    cv2.circle(img_a, (int(nose_2d[0]),int(nose_2d[1])), HEAD_R, rcol, 2)
                    if ftr.face_hits > 0 and ct - ftr._lfht < 0.4:
                        cv2.putText(img_a,"FACE!",(int(nose_2d[0])-20,int(nose_2d[1])+HEAD_R+18),FD,0.60,GRN,2)

                for wi, il in ((9, True), (10, False)):
                    if wi >= len(kp_a): continue
                    wx2d=kp_a[wi]; wx,wy=int(float(wx2d[0])),int(float(wx2d[1]))
                    if wx==0 and wy==0: continue
                    if not (0<=wx<CAM_W and 0<=wy<CAM_H): continue
                    glow(img_a, (wx,wy), GLOVE_R+4, rcol, n=2)
                    cv2.circle(img_a, (wx,wy), GLOVE_R, rcol, 2)
                    lx,ly=wx-28,wy-GLOVE_R-26
                    cv2.rectangle(img_a, (lx-4,ly-18), (lx+72,ly+4), BLK, -1)
                    cv2.putText(img_a, rlbl, (lx,ly), FD, 0.54, rcol, 2)
                    org_tag = origin.get(wi, '?')
                    org_c = GRN if org_tag in ('AB','ABC') else (YLW if org_tag=='A' else ORG)
                    cv2.putText(img_a, org_tag, (wx+GLOVE_R+2, wy+4), FS, 0.30, org_c, 1)
                    mode_tag = "TRK" if use_tracking else "YLO"
                    mode_col = CYN if use_tracking else GRN
                    cv2.putText(img_a, mode_tag, (wx+GLOVE_R+2, wy+16), FS, 0.28, mode_col, 1)
                    if pid_a == tp and self.tm:
                        pulse = int(5*math.sin(ct*9))+5
                        glow(img_a, (wx,wy), GLOVE_R+8+pulse, RED, n=2)

                    if ftr and can_det:
                        wp3 = pts3d.get(wi); sp3 = pts3d.get(5 if il else 6)
                        if wp3 is None: continue
                        try:
                            np2,spd,ptype,active = ftr.update_punch(wp3, il, sp3, ct)
                            if self.tm: self._ts['dv'] += 1
                            if active: cv2.circle(img_a, (wx,wy), GLOVE_R-4, ORG, -1)
                            if sp3:
                                ext_m = dist3d(wp3, sp3)
                                cv2.putText(img_a, f"{ext_m:.2f}m", (wx+GLOVE_R+2,wy-6),
                                            FS, 0.34, GRN if ext_m>EXTENSION_THR_M else YLW, 1)
                            if spd > 0.1:
                                cv2.putText(img_a, f"{spd:.1f}m/s", (wx-GLOVE_R-52,wy),
                                            FS, 0.34, CYN, 1)
                            if self.tm:
                                if spd>0 and math.isfinite(spd): self._ts['ss'].append(spd)
                                if sp3:
                                    e2 = dist3d(wp3,sp3)
                                    if math.isfinite(e2): self._ts['es'].append(e2)

                            if np2:
                                if self.tm:
                                    self._ts['pd'] += 1
                                    if ptype in self._ts['cc']: self._ts['cc'][ptype] += 1
                                if self.tm:
                                    hn = ftr.hL if il else ftr.hR
                                    pk = max((h.get('ext',0) for h in hn), default=0)
                                    hb=pk>EXTENSION_THR_M*2.5; hf=False; hbody=False
                                else:
                                    hb, hf, hbody = self._check_hit(wp3, pid_a)
                                hit_any = hb or hf or hbody
                                if hit_any:
                                    ftr.connected += 1
                                    if self.tm: self._ts['hd'] += 1
                                    if hf:
                                        ftr.face_hits += 1; ftr._lfht = ct
                                        cv2.putText(img_a,"FACE HIT!",(wx-36,wy+GLOVE_R+24),FD,0.66,GRN,2)
                                    elif hbody:
                                        ftr.body_hits += 1
                                        cv2.putText(img_a,"BODY HIT!",(wx-36,wy+GLOVE_R+24),FD,0.66,YLW,2)
                                    else:
                                        cv2.putText(img_a,"HIT!",(wx-20,wy+GLOVE_R+24),FD,0.66,GRN,2)
                                    glow(img_a,(wx,wy),GLOVE_R+10,GRN,n=3)
                                else:
                                    glow(img_a,(wx,wy),GLOVE_R+7,CYN,n=2)
                                cv2.putText(img_a,ptype,(wx-28,wy-GLOVE_R-22),FD,0.50,YLW,2)

                                # [8] FighterID API export
                                fighter_id = ("red" if ftr==self.red else "blue") if not self.tm else "test"
                                elbow_ang = ftr._elbow_angle(il)
                                ext_v = dist3d(wp3, sp3) if sp3 else 0.0
                                FAPI.send(fighter_id, ptype, spd, ext_v, hit_any, hf, hbody, elbow_ang)

                                # [9] Dataset capture
                                if DATASET_ENABLED:
                                    sh3 = pts3d.get(5 if il else 6)
                                    DATASET.log_event(fighter_id, "L" if il else "R",
                                                      ptype, spd, ext_v, hit_any, hf, hbody,
                                                      elbow_ang, sh3)
                        except Exception as _e_punch:
                            print(f"[punch] pid={pid_a} wi={wi}: {_e_punch}")

            # Timer logic
            rem = 0
            if self.session_state == "RUNNING":
                el = time.time()-self.t_start-self.t_paused
                if self.phase == "ROUND":
                    rem = max(0, int(ROUND_TIME - el))
                    if rem == 0:
                        self._end_round(); self.rnd_done += 1
                        if self.rnd_done >= TOTAL_ROUNDS:
                            self._log("=== SESIÓN TERMINADA ===")
                            self._emit_session_report()
                            if DATASET_ENABLED: DATASET.stop_session()
                            self.session_state="IDLE"; self.phase="IDLE"
                        else:
                            self.phase="REST"; self.t_start=time.time(); self.t_paused=0.0
                else:
                    rem = max(0, int(REST_TIME - el))
                    if rem == 0:
                        self.rnd += 1; self.phase="ROUND"
                        FAPI.advance_round(self.rnd)
                        self.t_start=time.time(); self.t_paused=0.0
                        self.red.reset(); self.blue.reset()
                        if self.tm: self._reset_ts()
            elif self.session_state == "PAUSED":
                el = self.t_pause-self.t_start-self.t_paused
                lim = ROUND_TIME if self.phase=="ROUND" else REST_TIME
                rem = max(0, int(lim-el))

            m2, s2 = rem//60, rem%60
            st, ph = self.session_state, self.phase
            ptxt, pc = (("IDLE",GRY) if st=="IDLE" else ("PAUSA",RED) if st=="PAUSED"
                        else ("LIVE",GRN) if ph=="ROUND" else ("REST",YLW))
            mtxt, mc = (("TEST",MAG) if self.tm else
                        ("FIGHT",CYN) if self.roles.mode=="fight" else ("DETECT",GRY))
            fps_vals = list(self._fps_counter)
            _fps_dt = (fps_vals[-1] - fps_vals[0]) if len(fps_vals) > 1 else 0.0
            eng_fps = len(fps_vals) / _fps_dt if _fps_dt > 1e-6 else 0.0

            # [10] Telemetry update
            self._telem['lat_a_ms']     = inf_a.last_latency_ms
            self._telem['lat_b_ms']     = inf_b.last_latency_ms
            self._telem['lat_c_ms']     = inf_c.last_latency_ms
            self._telem['total_infers'] = inf_a.total_infers + inf_b.total_infers + inf_c.total_infers
            self._telem['valid_stereo'] = n_3d
            self._telem['kp_per_frame'] = n_total
            self._telem['api_sent']     = FAPI.sent_ok
            self._telem['api_err']      = FAPI.sent_err

            def hud(img, label, lc):
                cv2.rectangle(img,(0,0),(CAM_W,58),BLK,-1)
                cv2.line(img,(0,57),(CAM_W,57),lc,2)
                tstxt = f"{m2:02d}:{s2:02d}"
                cv2.putText(img,tstxt,(CAM_W//2-52,44),FD,1.20,(40,40,50),4)
                cv2.putText(img,tstxt,(CAM_W//2-52,44),FD,1.20,WHT,2)
                cv2.putText(img,label,(10,38),FS,0.40,lc,1)
                cv2.putText(img,ptxt,(CAM_W-72,20),FS,0.40,pc,1)
                cv2.putText(img,mtxt,(CAM_W-72,54),FS,0.40,mc,1)

            trk_tag = "TRK" if use_tracking else "YLO"
            hud(img_a, f"CAM B·LAT1 · {eng_fps:.0f}fps · 3D:{n_3d}/{max(n_total,1)} · {trk_tag} · KAL", GRN)
            hud(img_b, f"CAM C·LAT2 · DEPTH REF · lat={inf_b.last_latency_ms:.0f}ms", MAG)
            hud(img_c, f"CAM A·CENITAL · BIOMECÁNICA · lat={inf_c.last_latency_ms:.0f}ms", CYN)

            # Pre-compute live scores — usa el scorer correspondiente al modo
            if self.tm:
                r_bx = BoxingScorer.compute(self._build_fighter_stat_dict(self.red))
                b_bx = BoxingScorer.compute(self._build_fighter_stat_dict(self.blue))
            else:
                r_bx = AggressivenessScorer.compute(self._build_fighter_stat_dict(self.red))
                b_bx = AggressivenessScorer.compute(self._build_fighter_stat_dict(self.blue))
            stats = {
                'rem':rem,'rnd':self.rnd,'phase':ph,'state':st,
                'mode':self.roles.mode,'mode_tm':self.tm,
                'status_msg':self._status_msg,'roles_ready':self.roles.ready,
                'eng_fps':round(eng_fps,1), 'gpu':_DEVICE.upper(),
                'tracking':use_tracking,
                'red':{
                    'strikes':self.red.strikes,'connected':self.red.connected,
                    'face_hits':self.red.face_hits,'body_hits':self.red.body_hits,
                    'accuracy':self.red.accuracy(),
                    'max_spd':round(self.red.max_spd_ms,2),'max_ext':round(self.red.max_ext_m,2),
                    'agility':self.red.head.agility(),'dodges':self.red.head.dodges,
                    'aggression':self.red.aggr,                           # nuevo
                    'score':round(self._score(self.red),1),
                    'ptypes':dict(self.red.ptypes),
                    'power_strikes':self.red.power_strikes,
                    'combo_count':self.red.combo_count,
                    'stance':self.red.stance,
                    'boxing_score':r_bx,
                    'glove_ok':self._glove_ok.get(self.roles.red_pid, False),
                    'punch_balance':self.red.punch_balance(),
                    'kinetic_chain':self.red.kinetic_chain_avg(),
                    'scoring_mode': 'test' if self.tm else 'fight',       # nuevo
                },
                # En TEST mode no hay esquina azul — dict vacío → GUI muestra "—"
                'blue': {} if self.tm else {
                    'strikes':self.blue.strikes,'connected':self.blue.connected,
                    'face_hits':self.blue.face_hits,'body_hits':self.blue.body_hits,
                    'accuracy':self.blue.accuracy(),
                    'max_spd':round(self.blue.max_spd_ms,2),'max_ext':round(self.blue.max_ext_m,2),
                    'agility':self.blue.head.agility(),'dodges':self.blue.head.dodges,
                    'aggression':self.blue.aggr,
                    'score':round(self._score(self.blue),1),
                    'ptypes':dict(self.blue.ptypes),
                    'power_strikes':self.blue.power_strikes,
                    'combo_count':self.blue.combo_count,
                    'stance':self.blue.stance,
                    'boxing_score':b_bx,
                    'glove_ok':self._glove_ok.get(self.roles.blue_pid, False),
                    'punch_balance':self.blue.punch_balance(),
                    'kinetic_chain':self.blue.kinetic_chain_avg(),
                    'scoring_mode': 'fight',
                },
                'rnd_winners':dict(self.rnd_winners),
                'n_3d':n_3d,'n_kp':n_total,'baseline':self.stereo_ab.B,
                'telem': dict(self._telem),
            }
            with self._lock:
                self._frame_a = img_a.copy()
                self._frame_b = img_b.copy()
                self._frame_c = img_c.copy()
                self._stats   = stats

        inf_a.stop(); inf_b.stop(); inf_c.stop()
        rdr_a.stop()
        if rdr_b: rdr_b.stop()
        if rdr_c: rdr_c.stop()
        time.sleep(0.2)  # esperar que los readers salgan antes de liberar caps
        try: cap_a.release()
        except Exception as e: print(f"[cleanup] cap_a.release: {e}")
        try:
            if cap_b: cap_b.release()
        except Exception as e: print(f"[cleanup] cap_b.release: {e}")
        try:
            if cap_c: cap_c.release()
        except Exception as e: print(f"[cleanup] cap_c.release: {e}")
        print(f"[VisionEngine] thread terminado (A={self.cam_a_idx} B={self.cam_b_idx} C={self.cam_c_idx})")

# ══════════════════════════════════════════════════════════════════
#  STAT CARD
# ══════════════════════════════════════════════════════════════════
class StatCard(ctk.CTkFrame):
    def __init__(self, parent, label, value="—", unit="", accent=GUI_CYAN, **kw):
        super().__init__(parent, fg_color=GUI_CARD, corner_radius=8, **kw)
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=10,weight="bold"),
                     text_color=GUI_GRAY).pack(anchor="w", padx=8, pady=(6,0))
        self._val = ctk.CTkLabel(self, text=value,
                                 font=ctk.CTkFont("Courier New",20,weight="bold"),
                                 text_color=accent)
        self._val.pack(anchor="w", padx=8)
        ctk.CTkLabel(self, text=unit if unit else " ",
                     font=ctk.CTkFont(size=8), text_color=GUI_GRAY
                     ).pack(anchor="w", padx=8, pady=(0,6))

    def set(self, value): self._val.configure(text=str(value))

# ══════════════════════════════════════════════════════════════════
#  [4] CALIBRATION DIALOG
# ══════════════════════════════════════════════════════════════════
class CalibDialog(ctk.CTkToplevel):
    def __init__(self, parent, engine):
        super().__init__(parent)
        self.title("Calibración Estéreo — Tablero 9×6")
        self.geometry("480x360"); self.resizable(False, False)
        self.configure(fg_color=GUI_BG)
        self._engine   = engine
        self._calibrator = StereoCalibrator()
        self._capturing = False
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Calibración Estéreo  CAM A + CAM B",
                     font=ctk.CTkFont(size=14,weight="bold"), text_color=GUI_CYAN
                     ).pack(pady=(16,4))
        ctk.CTkLabel(self, text="Imprime un tablero 9×6 cuadros de 25mm.\n"
                                "Muéstralo desde ángulos distintos ante ambas cámaras.",
                     font=ctk.CTkFont(size=11), text_color=GUI_GRAY, justify="center"
                     ).pack(pady=4)
        self._status = ctk.CTkLabel(self, text="Capturas: 0 / 10",
                                    font=ctk.CTkFont("Courier New",13,weight="bold"),
                                    text_color=GUI_WHITE)
        self._status.pack(pady=8)
        self._rms_lbl = ctk.CTkLabel(self, text="RMS: —",
                                     font=ctk.CTkFont("Courier New",11), text_color=GUI_GRAY)
        self._rms_lbl.pack()
        btn_row = ctk.CTkFrame(self, fg_color="transparent"); btn_row.pack(pady=16)
        ctk.CTkButton(btn_row, text="📸  CAPTURAR",
                      fg_color=GUI_GREEN, text_color=GUI_BG,
                      font=ctk.CTkFont(size=12,weight="bold"), width=140,
                      command=self._do_capture).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="✔  CALIBRAR",
                      fg_color=GUI_CYAN, text_color=GUI_BG,
                      font=ctk.CTkFont(size=12,weight="bold"), width=140,
                      command=self._do_calibrate).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="✕  CERRAR",
                      fg_color=GUI_PANEL, text_color=GUI_WHITE, border_color=GUI_BORDER,
                      border_width=1, width=100, command=self.destroy
                      ).pack(side="left", padx=8)

    def _do_capture(self):
        if self._engine is None: return
        fa, fb, _ = self._engine.get_frames()
        if fa is None or fb is None:
            self._status.configure(text="⚠ Sin frames de cámara"); return
        ok = self._calibrator.capture(fa, fb)
        n  = self._calibrator.n_captures
        col = GUI_GREEN if ok else GUI_RED
        txt = f"Capturas: {n} / 10  {'✔' if ok else '✗ (tablero no detectado)'}"
        self._status.configure(text=txt, text_color=col)

    def _do_calibrate(self):
        try:
            h, w = 1080, 1920
            bl, f, cx, cy, rms = self._calibrator.calibrate((w, h))
            # Hot-apply to engine
            if self._engine:
                with self._engine._lock:
                    self._engine.stereo_ab.B  = bl
                    self._engine.stereo_ab.f  = f
                    self._engine.stereo_ab.cx = cx
                    self._engine.stereo_ab.cy = cy
                    self._engine.stereo_ac.B  = bl * 1.2
                    self._engine.stereo_ac.f  = f
                    self._engine.stereo_ac.cx = cx
                    self._engine.stereo_ac.cy = cy
            self._rms_lbl.configure(
                text=f"RMS: {rms:.4f}  BL={bl:.3f}m  f={f:.0f}px",
                text_color=GUI_GREEN if rms < 1.0 else GUI_YELLOW)
            self._status.configure(text="✔ Calibración guardada", text_color=GUI_GREEN)
        except Exception as e:
            self._status.configure(text=f"Error: {e}", text_color=GUI_RED)

# ══════════════════════════════════════════════════════════════════
#  STREAM CONFIG DIALOG
# ══════════════════════════════════════════════════════════════════
class _StreamConfigDialog(ctk.CTkToplevel):
    """Diálogo de configuración Supabase + RTMP para la transmisión en vivo."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configuración — EN VIVO · fighter-id.org")
        self.geometry("560x420")
        self.resizable(False, False)
        self.configure(fg_color=GUI_BG)
        self.grab_set()   # modal
        self._build()

    def _build(self):
        pad = dict(padx=20, pady=6)

        ctk.CTkLabel(self, text="⚙  Configuración de Transmisión en Vivo",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=GUI_CYAN).pack(pady=(18, 4))

        ctk.CTkLabel(self, text="Supabase (estadísticas en tiempo real)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=GUI_YELLOW).pack(anchor="w", **pad)

        # Supabase URL
        ctk.CTkLabel(self, text="Project URL  (https://xxxx.supabase.co)",
                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(anchor="w", padx=20, pady=(0, 2))
        self._supa_url = ctk.CTkEntry(self, width=520, placeholder_text="https://xxxx.supabase.co")
        self._supa_url.pack(padx=20)
        if SUPABASE_URL:
            self._supa_url.insert(0, SUPABASE_URL)

        # Supabase Anon Key
        ctk.CTkLabel(self, text="Anon Key  (eyJ...)",
                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(anchor="w", padx=20, pady=(8, 2))
        self._supa_key = ctk.CTkEntry(self, width=520, placeholder_text="eyJ...", show="*")
        self._supa_key.pack(padx=20)
        if SUPABASE_ANON_KEY:
            self._supa_key.insert(0, SUPABASE_ANON_KEY)

        ctk.CTkLabel(self, text="Video RTMP  (opcional)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=GUI_YELLOW).pack(anchor="w", padx=20, pady=(14, 2))

        # RTMP URL
        ctk.CTkLabel(self, text="RTMP URL  (rtmp://...  — YouTube, Twitch, Mux, etc.)",
                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(anchor="w", padx=20, pady=(0, 2))
        self._rtmp_url = ctk.CTkEntry(self, width=520, placeholder_text="rtmp://a.rtmp.youtube.com/live2/xxxx-xxxx")
        self._rtmp_url.pack(padx=20)
        if STREAM_RTMP_URL:
            self._rtmp_url.insert(0, STREAM_RTMP_URL)

        # Status label
        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color=GUI_GREEN)
        self._status.pack(pady=(10, 0))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="💾  GUARDAR",
                      fg_color=GUI_CYAN, text_color=GUI_BG,
                      font=ctk.CTkFont(size=12, weight="bold"), width=160,
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="✕  CANCELAR",
                      fg_color=GUI_PANEL, text_color=GUI_WHITE, border_color=GUI_BORDER,
                      border_width=1, width=120, command=self.destroy).pack(side="left", padx=8)

    def _save(self):
        global SUPABASE_URL, SUPABASE_ANON_KEY, STREAM_RTMP_URL
        SUPABASE_URL      = self._supa_url.get().strip()
        SUPABASE_ANON_KEY = self._supa_key.get().strip()
        STREAM_RTMP_URL   = self._rtmp_url.get().strip()
        _save_stream_config()
        self._status.configure(text="✔  Configuración guardada correctamente", text_color=GUI_GREEN)
        self.after(1200, self.destroy)


# ══════════════════════════════════════════════════════════════════
#  OFFICIAL SESSION DIALOG
# ══════════════════════════════════════════════════════════════════
class OfficialSessionDialog(ctk.CTkToplevel):
    """
    Carga perfiles de peleadores desde Supabase fighter_profiles,
    permite seleccionar esquina roja y azul, número de rounds,
    y crea la sesión en fight_telemetry_sessions antes de iniciar.
    """
    def __init__(self, parent, engine):
        super().__init__(parent)
        self.title("Sesión Oficial — Perfiles de Peleadores")
        self.geometry("540x500")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=GUI_BG)
        self._engine   = engine
        self._profiles = []
        self._red_id   = None
        self._blue_id  = None
        self._build()
        self.after(120, self._load_fighters)

    def _build(self):
        ctk.CTkLabel(self, text="SESIÓN OFICIAL",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=GUI_CYAN).pack(pady=(16, 2))
        ctk.CTkLabel(self, text="Selecciona los peleadores registrados en la base de datos",
                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(pady=(0, 10))

        # ── Esquina Roja ──────────────────────────────────────────
        red_f = ctk.CTkFrame(self, fg_color=GUI_PANEL, corner_radius=8)
        red_f.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(red_f, text="🔴  ESQUINA ROJA",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=GUI_RED).pack(anchor="w", padx=12, pady=(8, 2))
        self._red_var = ctk.StringVar(value="— cargando perfiles... —")
        self._red_cb  = ctk.CTkOptionMenu(
            red_f, variable=self._red_var, values=["— cargando perfiles... —"],
            fg_color=GUI_CARD, button_color="#6a1a1a", text_color=GUI_WHITE,
            font=ctk.CTkFont(size=11), command=self._on_red_select)
        self._red_cb.pack(fill="x", padx=12, pady=(0, 8))

        # ── Esquina Azul ──────────────────────────────────────────
        blue_f = ctk.CTkFrame(self, fg_color=GUI_PANEL, corner_radius=8)
        blue_f.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(blue_f, text="🔵  ESQUINA AZUL",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=GUI_BLUE).pack(anchor="w", padx=12, pady=(8, 2))
        self._blue_var = ctk.StringVar(value="— cargando perfiles... —")
        self._blue_cb  = ctk.CTkOptionMenu(
            blue_f, variable=self._blue_var, values=["— cargando perfiles... —"],
            fg_color=GUI_CARD, button_color="#1a1a6a", text_color=GUI_WHITE,
            font=ctk.CTkFont(size=11), command=self._on_blue_select)
        self._blue_cb.pack(fill="x", padx=12, pady=(0, 8))

        # ── Rounds ────────────────────────────────────────────────
        rounds_f = ctk.CTkFrame(self, fg_color="transparent")
        rounds_f.pack(fill="x", padx=20, pady=(6, 2))
        ctk.CTkLabel(rounds_f, text="Rounds:",
                     font=ctk.CTkFont(size=11), text_color=GUI_WHITE).pack(side="left", padx=(0, 10))
        self._rounds_var = ctk.StringVar(value="3")
        for r in ["1", "2", "3", "4", "5"]:
            ctk.CTkRadioButton(
                rounds_f, text=r, variable=self._rounds_var, value=r,
                font=ctk.CTkFont(size=11), fg_color=GUI_CYAN, border_color=GUI_BORDER
            ).pack(side="left", padx=6)

        # ── Info card ─────────────────────────────────────────────
        self._info_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Courier New", 9), text_color=GUI_GRAY,
            justify="left", anchor="w")
        self._info_lbl.pack(fill="x", padx=24, pady=(6, 2))

        # ── Status ────────────────────────────────────────────────
        self._status = ctk.CTkLabel(self, text="Conectando a Supabase…",
                                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY)
        self._status.pack(pady=4)

        # ── Buttons ───────────────────────────────────────────────
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.pack(pady=14)
        self._ok_btn = ctk.CTkButton(
            btn_f, text="✔  CREAR SESIÓN OFICIAL",
            fg_color=GUI_GREEN, text_color=GUI_BG,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=220, state="disabled", command=self._create_session)
        self._ok_btn.pack(side="left", padx=8)
        ctk.CTkButton(
            btn_f, text="✕  CANCELAR",
            fg_color=GUI_PANEL, text_color=GUI_WHITE,
            border_color=GUI_BORDER, border_width=1,
            width=120, command=self.destroy).pack(side="left", padx=8)

    # ── Internal helpers ──────────────────────────────────────────

    def _profile_label(self, p):
        parts = [p.get("name", "—")]
        if p.get("nickname"):    parts.append(f'"{p["nickname"]}"')
        if p.get("weight_class"): parts.append(f'[{p["weight_class"]}]')
        return "  ".join(parts)

    def _load_fighters(self):
        def _fetch():
            profiles = FAPI.list_fighter_profiles()
            self.after(0, lambda: self._on_fighters_loaded(profiles))
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_fighters_loaded(self, profiles):
        self._profiles = profiles
        if not profiles:
            self._status.configure(
                text="⚠ Sin perfiles en DB. Crea peleadores en Supabase primero.",
                text_color=GUI_ORANGE)
            self._red_cb.configure(values=["— sin perfiles —"])
            self._blue_cb.configure(values=["— sin perfiles —"])
            return
        labels = [self._profile_label(p) for p in profiles]
        self._red_cb.configure(values=labels)
        self._blue_cb.configure(values=labels)
        self._red_var.set(labels[0])
        self._blue_var.set(labels[min(1, len(labels) - 1)])
        self._red_id  = profiles[0]["id"]
        self._blue_id = profiles[min(1, len(profiles) - 1)]["id"]
        self._status.configure(
            text=f"{len(profiles)} peleador(es) cargado(s) desde Supabase",
            text_color=GUI_GREEN)
        self._ok_btn.configure(state="normal")
        self._update_info()

    def _on_red_select(self, val):
        for p in self._profiles:
            if self._profile_label(p) == val:
                self._red_id = p["id"]; break
        self._update_info()

    def _on_blue_select(self, val):
        for p in self._profiles:
            if self._profile_label(p) == val:
                self._blue_id = p["id"]; break
        self._update_info()

    def _update_info(self):
        lines = []
        for corner, pid in [("ROJO", self._red_id), ("AZUL", self._blue_id)]:
            for p in self._profiles:
                if p["id"] == pid:
                    gym    = p.get("gym") or "—"
                    fights = p.get("total_fights", 0)
                    acc    = p.get("accuracy", 0.0)
                    lines.append(
                        f"{corner}: {p.get('name','?')}"
                        f"  |  Gym: {gym}"
                        f"  |  Peleas: {fights}"
                        f"  |  Precisión hist.: {acc*100:.0f}%")
        self._info_lbl.configure(text="\n".join(lines))

    def _create_session(self):
        if not self._red_id or not self._blue_id:
            self._status.configure(text="⚠ Selecciona ambos peleadores", text_color=GUI_ORANGE)
            return
        if self._red_id == self._blue_id:
            self._status.configure(text="⚠ Los peleadores deben ser diferentes", text_color=GUI_ORANGE)
            return
        rounds = int(self._rounds_var.get())
        self._ok_btn.configure(state="disabled", text="Creando sesión…")
        self._status.configure(text="Creando sesión en Supabase…", text_color=GUI_GRAY)

        def _do():
            row = FAPI.create_fight_session(self._red_id, self._blue_id, rounds)
            self.after(0, lambda: self._on_session_created(row, rounds))
        threading.Thread(target=_do, daemon=True).start()

    def _on_session_created(self, row, rounds):
        if not row:
            self._status.configure(
                text="❌ Error al crear sesión — verifica credenciales Supabase",
                text_color=GUI_RED)
            self._ok_btn.configure(state="normal", text="✔  CREAR SESIÓN OFICIAL")
            return
        global TOTAL_ROUNDS
        TOTAL_ROUNDS = rounds
        # Load fighter names so they display correctly in the engine
        FAPI._load_fighters(row)
        red_name  = FAPI._fighter_red_name
        blue_name = FAPI._fighter_blue_name
        self._status.configure(
            text=f"✔ Sesión creada: {red_name} vs {blue_name}",
            text_color=GUI_GREEN)
        self._engine._log(
            f"SESIÓN OFICIAL lista: {red_name} vs {blue_name}  ({rounds} rounds)")
        self._engine._status_msg = (
            f"Oficial: {red_name} vs {blue_name} — asigna roles ROJO/AZUL y presiona ▶ INICIAR")
        self.after(1800, self.destroy)


# ══════════════════════════════════════════════════════════════════
#  [10] TELEMETRY PANEL
# ══════════════════════════════════════════════════════════════════
class TelemPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=GUI_PANEL, corner_radius=8, **kw)
        ctk.CTkLabel(self, text="TELEMETRÍA",
                     font=ctk.CTkFont(size=9,weight="bold"),
                     text_color=GUI_GRAY).pack(anchor="w", padx=10, pady=(6,2))
        self._lbl = ctk.CTkLabel(self, text="—",
                                  font=ctk.CTkFont("Courier New",9),
                                  text_color=GUI_GRAY, justify="left")
        self._lbl.pack(anchor="w", padx=10, pady=(0,6))

    def update_telem(self, telem: dict):
        la = telem.get('lat_a_ms', 0); lb = telem.get('lat_b_ms', 0); lc = telem.get('lat_c_ms', 0)
        n3 = telem.get('valid_stereo', 0); kp = telem.get('kp_per_frame', 0)
        ti = telem.get('total_infers', 0)
        api_ok = telem.get('api_sent', 0); api_err = telem.get('api_err', 0)
        txt = (f"Lat A:{la:.0f}ms  B:{lb:.0f}ms  C:{lc:.0f}ms\n"
               f"Infers:{ti}  3D:{n3}/{max(kp,1)}  KP:{kp}\n"
               f"API OK:{api_ok} ERR:{api_err}")
        self._lbl.configure(text=txt)

# ══════════════════════════════════════════════════════════════════
#  MAIN GUI v4
# ══════════════════════════════════════════════════════════════════
class FighterIDApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("FighterID Vision v4.3  —  3-Camera · Kalman · Hungarian · Pro Boxing")
        self.configure(fg_color=GUI_BG)
        sw=self.winfo_screenwidth(); sh=self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        try: self.state('zoomed')         # Windows / mayoría de Linux DEs
        except: self.attributes('-zoomed', True)
        self._engine: VisionEngine = None
        self._live:   LiveStreamManager = None
        self._running = False
        self._sel_a = self._sel_b = self._sel_c = None
        self._build_ui()
        self.after(300, self._init_cameras)
        self.after(2000, self._refresh_live_status)  # actualizar etiqueta de stats

    def _build_ui(self):
        top = ctk.CTkFrame(self, height=52, fg_color=GUI_PANEL, corner_radius=0)
        top.pack(fill="x", side="top"); top.pack_propagate(False)
        ctk.CTkLabel(top, text="FIGHTER ID  v4.3",
                     font=ctk.CTkFont("Courier New",16,weight="bold"),
                     text_color=GUI_CYAN).pack(side="left", padx=18, pady=12)
        self._top_status = ctk.CTkLabel(top, text="Escaneando...",
                                        font=ctk.CTkFont(size=11), text_color=GUI_GRAY)
        self._top_status.pack(side="left", padx=10)
        self._trk_lbl = ctk.CTkLabel(top, text="—",
                                     font=ctk.CTkFont("Courier New",10), text_color=GUI_GRAY)
        self._trk_lbl.pack(side="right", padx=6)
        self._gpu_lbl = ctk.CTkLabel(top, text=f"GPU: {_DEVICE.upper()}",
                                     font=ctk.CTkFont("Courier New",11,weight="bold"),
                                     text_color=GUI_GREEN if _DEVICE!="cpu" else GUI_YELLOW)
        self._gpu_lbl.pack(side="right", padx=10)
        self._fps_lbl = ctk.CTkLabel(top, text="—fps",
                                     font=ctk.CTkFont("Courier New",13,weight="bold"),
                                     text_color=GUI_GRAY)
        self._fps_lbl.pack(side="right", padx=6)
        self._timer_lbl = ctk.CTkLabel(top, text="03:00",
                                       font=ctk.CTkFont("Courier New",26,weight="bold"),
                                       text_color=GUI_WHITE)
        self._timer_lbl.pack(side="right", padx=24)
        self._round_lbl = ctk.CTkLabel(top, text="ROUND 1",
                                       font=ctk.CTkFont(size=13,weight="bold"),
                                       text_color=GUI_WHITE)
        self._round_lbl.pack(side="right", padx=4)
        self._phase_lbl = ctk.CTkLabel(top, text="IDLE",
                                       font=ctk.CTkFont(size=11,weight="bold"),
                                       text_color=GUI_GRAY)
        self._phase_lbl.pack(side="right", padx=10)
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)
        sidebar = ctk.CTkFrame(main, width=200, fg_color=GUI_PANEL, corner_radius=0)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)
        center = ctk.CTkFrame(main, fg_color=GUI_BG)
        center.pack(side="left", fill="both", expand=True)
        self._build_center(center)

    def _build_sidebar(self, parent):
        B = dict(corner_radius=7, height=34, font=ctk.CTkFont(size=11,weight="bold"))
        def sep(): ctk.CTkFrame(parent, height=1, fg_color=GUI_BORDER).pack(fill="x", padx=12, pady=6)
        def lbl(t): ctk.CTkLabel(parent, text=t,
                                  font=ctk.CTkFont(size=9,weight="bold"),
                                  text_color=GUI_GRAY).pack(anchor="w", padx=14, pady=(5,1))
        ctk.CTkFrame(parent, height=10, fg_color="transparent").pack()
        lbl("CÁMARA A  ↑ CENITAL (top)")
        self._cb_a = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_GREEN,
                                     button_color=GUI_GREEN, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('A',v))
        self._cb_a.pack(fill="x", padx=12, pady=2)
        lbl("CÁMARA B  → LATERAL 1  (IA)")
        self._cb_b = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_MAGENTA,
                                     button_color=GUI_MAGENTA, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('B',v))
        self._cb_b.pack(fill="x", padx=12, pady=2)
        lbl("CÁMARA C  → LATERAL 2  (depth)")
        self._cb_c = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_CYAN,
                                     button_color=GUI_CYAN, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('C',v))
        self._cb_c.pack(fill="x", padx=12, pady=2)
        self._apply_btn = ctk.CTkButton(
                      parent, text="⟳  APLICAR CÁMARAS", fg_color=GUI_PANEL,
                      text_color=GUI_CYAN, border_color=GUI_CYAN, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_apply_cams,
                      corner_radius=7, height=30,
                      font=ctk.CTkFont(size=10,weight="bold"))
        self._apply_btn.pack(fill="x", padx=12, pady=4)
        sep(); lbl("SESIÓN")
        ctk.CTkButton(parent, text="🧪  TEST RÁPIDO",
                      fg_color="#0d1a2a", text_color=GUI_CYAN,
                      border_color=GUI_CYAN, border_width=1,
                      hover_color="#122030",
                      command=self._cmd_quick_test, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="🥊  SESIÓN OFICIAL",
                      fg_color="#0a1a0a", text_color=GUI_GREEN,
                      border_color=GUI_GREEN, border_width=1,
                      hover_color="#0f220f",
                      command=self._cmd_oficial, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="▶  INICIAR", fg_color=GUI_GREEN,
                      text_color=GUI_BG, hover_color="#28b84e",
                      command=self._cmd_start, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⏸  PAUSA", fg_color=GUI_YELLOW,
                      text_color=GUI_BG, hover_color="#c0a010",
                      command=self._cmd_pause, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⏹  FIN ROUND", fg_color=GUI_RED,
                      text_color=GUI_WHITE, hover_color="#b02020",
                      command=self._cmd_end, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⏏  FIN SESIÓN", fg_color="#200808",
                      text_color=GUI_RED, border_color="#602020", border_width=1,
                      hover_color="#2e0d0d",
                      command=self._cmd_end_session, **B).pack(fill="x", padx=12, pady=2)
        sep(); lbl("ROLES")
        ctk.CTkButton(parent, text="⬜  TEST", fg_color=GUI_PANEL,
                      text_color=GUI_WHITE, border_color=GUI_BORDER, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_test, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="🔴  ROJO", fg_color="#3a1010",
                      text_color=GUI_RED, border_color=GUI_RED, border_width=1,
                      hover_color="#4a1818", command=self._cmd_red, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="🔵  AZUL", fg_color="#10103a",
                      text_color=GUI_BLUE, border_color=GUI_BLUE, border_width=1,
                      hover_color="#18184a", command=self._cmd_blue, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="✕  LIMPIAR", fg_color=GUI_PANEL,
                      text_color=GUI_ORANGE, border_color=GUI_ORANGE, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_clear, **B).pack(fill="x", padx=12, pady=2)
        sep(); lbl("HERRAMIENTAS v4")
        ctk.CTkButton(parent, text="📐  CALIBRAR", fg_color="#0a1a2a",
                      text_color=GUI_CYAN, border_color=GUI_CYAN, border_width=1,
                      hover_color="#0d2035", command=self._cmd_calib, **B).pack(fill="x", padx=12, pady=2)
        self._dataset_btn = ctk.CTkButton(parent, text="💾  DATASET: OFF",
                      fg_color=GUI_PANEL, text_color=GUI_GRAY,
                      border_color=GUI_BORDER, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_dataset_toggle, **B)
        self._dataset_btn.pack(fill="x", padx=12, pady=2)
        self._api_btn = ctk.CTkButton(parent, text="🌐  API: OFF",
                      fg_color=GUI_PANEL, text_color=GUI_GRAY,
                      border_color=GUI_BORDER, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_api_toggle, **B)
        self._api_btn.pack(fill="x", padx=12, pady=2)
        sep(); lbl("INFER_EVERY")
        self._infer_entry = ctk.CTkEntry(parent, placeholder_text="6",
                                         fg_color=GUI_CARD, border_color=GUI_BORDER, height=30)
        self._infer_entry.insert(0, str(INFER_EVERY)); self._infer_entry.pack(fill="x", padx=12, pady=2)
        sep(); lbl("BASELINE A↔B (m)")
        self._bl_entry = ctk.CTkEntry(parent, placeholder_text="1.50",
                                      fg_color=GUI_CARD, border_color=GUI_BORDER, height=30)
        self._bl_entry.insert(0, str(DEFAULT_BASELINE)); self._bl_entry.pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="↺  APLICAR", fg_color=GUI_PANEL,
                      text_color=GUI_CYAN, border_color=GUI_CYAN, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_apply_baseline, **B
                      ).pack(fill="x", padx=12, pady=2)
        sep()
        self._stereo_lbl = ctk.CTkLabel(parent, text="3D: —/—",
                                        font=ctk.CTkFont("Courier New",12,weight="bold"),
                                        text_color=GUI_GREEN)
        self._stereo_lbl.pack(padx=14, anchor="w")
        # [10] Telemetry panel
        self._telem_panel = TelemPanel(parent)
        self._telem_panel.pack(fill="x", padx=12, pady=4)
        self._status_lbl = ctk.CTkLabel(parent, text="",
                                        font=ctk.CTkFont(size=9), text_color=GUI_GRAY,
                                        wraplength=185, justify="left")
        self._status_lbl.pack(padx=14, anchor="w", pady=(4,0))
        sep(); lbl("EN VIVO  ·  fighter-id.org")
        self._live_btn = ctk.CTkButton(
            parent, text="🔴  EN VIVO: OFF",
            fg_color="#1a0808", text_color=GUI_RED,
            border_color="#602020", border_width=1,
            hover_color="#2a0d0d",
            command=self._cmd_live_toggle,
            **B)
        self._live_btn.pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(
            parent, text="⚙  CONFIGURAR STREAM",
            fg_color=GUI_PANEL, text_color=GUI_GRAY,
            border_color=GUI_BORDER, border_width=1,
            hover_color=GUI_CARD,
            command=self._cmd_live_config,
            **B).pack(fill="x", padx=12, pady=2)
        self._live_stat_lbl = ctk.CTkLabel(
            parent, text="Supabase: —  |  RTMP: —",
            font=ctk.CTkFont("Courier New", 8), text_color=GUI_GRAY,
            wraplength=185, justify="left")
        self._live_stat_lbl.pack(padx=14, anchor="w", pady=(2,0))
        sep(); lbl("REGISTRO")
        self._log_box = ctk.CTkTextbox(parent, fg_color=GUI_CARD, text_color=GUI_GRAY,
                                       font=ctk.CTkFont("Courier New",8),
                                       wrap="word", corner_radius=6)
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0,12))

    def _build_center(self, parent):
        cam_row = ctk.CTkFrame(parent, fg_color="transparent")
        cam_row.pack(fill="both", expand=True, padx=4, pady=(4,2))
        self._cam_lbls = []
        self._cam_title_lbls = []   # referencias para actualizar tras "Aplicar"
        self._cam_info_lbls  = []   # subtítulo: [índice] nombre  fps
        _CAM_DEFS = [
            ("CAM A  ·  CENITAL TOP",   GUI_GREEN),
            ("CAM B  ·  IA + KALMAN",   GUI_MAGENTA),
            ("CAM C  ·  DEPTH REF",     GUI_CYAN),
        ]
        for title, color in _CAM_DEFS:
            f = ctk.CTkFrame(cam_row, fg_color=GUI_CARD, corner_radius=10)
            f.pack(side="left", fill="both", expand=True, padx=3)
            tl = ctk.CTkLabel(f, text=title,
                              font=ctk.CTkFont(size=9,weight="bold"),
                              text_color=color)
            tl.pack(pady=(6,0))
            self._cam_title_lbls.append(tl)
            # subtítulo con índice + nombre real del dispositivo (se completa al aplicar)
            il = ctk.CTkLabel(f, text="—  esperando cámaras…",
                              font=ctk.CTkFont("Courier New", 8),
                              text_color=GUI_GRAY)
            il.pack(pady=(0,2))
            self._cam_info_lbls.append(il)
            lbl = ctk.CTkLabel(f, text="", fg_color=GUI_BLACK)
            lbl.pack(fill="both", expand=True, padx=4, pady=(0,4))
            self._cam_lbls.append(lbl)
        stats_bar = ctk.CTkFrame(parent, fg_color=GUI_PANEL, height=220, corner_radius=0)
        stats_bar.pack(fill="x"); stats_bar.pack_propagate(False)
        info = ctk.CTkFrame(stats_bar, fg_color="transparent", height=32)
        info.pack(fill="x", padx=14, pady=(6,0)); info.pack_propagate(False)
        ctk.CTkLabel(info, text="Rounds:",
                     font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(side="left")
        self._round_badges = []
        for i in range(TOTAL_ROUNDS):
            b = ctk.CTkLabel(info, text=str(i+1), width=28, height=28,
                             font=ctk.CTkFont("Courier New",11,weight="bold"),
                             fg_color=GUI_CARD, text_color=GUI_GRAY, corner_radius=14)
            b.pack(side="left", padx=3); self._round_badges.append(b)
        cards = ctk.CTkFrame(stats_bar, fg_color="transparent")
        cards.pack(fill="both", expand=True, padx=8, pady=(4,8))
        self._rc = self._fighter_panel(cards, "ESQUINA ROJA", GUI_RED)
        ctk.CTkFrame(cards, width=2, fg_color=GUI_BORDER).pack(side="left", fill="y", padx=4)
        self._bc = self._fighter_panel(cards, "ESQUINA AZUL", GUI_BLUE)

    def _fighter_panel(self, parent, title, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(f, text=f"● {title}",
                     font=ctk.CTkFont(size=11,weight="bold"), text_color=color
                     ).pack(anchor="w", padx=8, pady=(4,2))
        # indicador de modo de puntuación (se actualiza desde _update_gui)
        mode_lbl = ctk.CTkLabel(f, text="MODO PELEA  ·  Agresividad + Evasión",
                                font=ctk.CTkFont(size=8, weight="bold"),
                                text_color=GUI_GRAY)
        mode_lbl.pack(anchor="w", padx=10, pady=(0,3))
        grid = ctk.CTkFrame(f, fg_color="transparent"); grid.pack(fill="x", padx=4)
        defs = [("strikes","GOLPES",""),("connected","HITS",""),
                ("accuracy","PREC","%"),("face_hits","CARA",""),
                ("body_hits","CUERPO",""),
                ("max_spd","VEL MÁX","m/s"),("aggression","AGRES",""),
                ("agility","AGIL",""),("dodges","ESQV",""),("score","SCORE","")]
        cards = {}
        for i, (k, lb, unit) in enumerate(defs):
            c = StatCard(grid, lb, unit=unit, accent=color)
            c.grid(row=i//5, column=i%5, padx=2, pady=2, sticky="ew")
            grid.columnconfigure(i%5, weight=1); cards[k] = c
        cards['_mode'] = mode_lbl   # guardar referencia al modo label
        # Glove indicator label
        glove_lbl = ctk.CTkLabel(f, text="⬜ SIN GUANTES",
                                  font=ctk.CTkFont(size=9, weight="bold"),
                                  text_color=GUI_ORANGE)
        glove_lbl.pack(anchor="w", padx=10, pady=(0,1)); cards['_glove'] = glove_lbl
        tl = ctk.CTkLabel(f, text="", font=ctk.CTkFont("Courier New",10),
                           text_color=GUI_GRAY, justify="left")
        tl.pack(anchor="w", padx=10, pady=(0,4)); cards['_tl'] = tl
        return cards

    def _init_cameras(self):
        global ALL_CAMERAS
        self._top_status.configure(text="Escaneando cámaras (Camo/1080p)...", text_color=GUI_GRAY)
        self.update()
        ALL_CAMERAS = scan_all_cameras()
        if not ALL_CAMERAS:
            self._top_status.configure(text="❌ Sin cámaras", text_color=GUI_RED); return
        labels    = [c['label'] for c in ALL_CAMERAS]
        none_opt  = ["— ninguna —"]
        self._cb_a.configure(values=labels)
        self._cb_b.configure(values=none_opt + labels)
        self._cb_c.configure(values=none_opt + labels)
        if len(ALL_CAMERAS) >= 1:
            self._cb_a.set(ALL_CAMERAS[0]['label']); self._sel_a = ALL_CAMERAS[0]['index']
        if len(ALL_CAMERAS) >= 2:
            self._cb_b.set(ALL_CAMERAS[1]['label']); self._sel_b = ALL_CAMERAS[1]['index']
        else:
            self._cb_b.set("— ninguna —"); self._sel_b = None
        if len(ALL_CAMERAS) >= 3:
            self._cb_c.set(ALL_CAMERAS[2]['label']); self._sel_c = ALL_CAMERAS[2]['index']
        else:
            self._cb_c.set("— ninguna —"); self._sel_c = None
        self._top_status.configure(
            text=f"{len(ALL_CAMERAS)} dispositivo(s) — presiona ⟳ APLICAR", text_color=GUI_CYAN)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_cam_select(self, slot, value):
        idx = None
        for c in ALL_CAMERAS:
            if c['label'] == value: idx = c['index']; break
        if slot=='A': self._sel_a = idx
        elif slot=='B': self._sel_b = idx
        else: self._sel_c = idx

    def _cmd_apply_cams(self):
        # Prevent double-click during startup
        if hasattr(self, '_apply_btn'):
            self._apply_btn.configure(state="disabled", text="⟳  Aplicando...")
        self.update()

        if self._engine:
            self._engine.cmd_stop()
            # Join with timeout — ensures previous thread fully exits before
            # opening cameras again (prevents cap.release() crash from 2 threads)
            self._engine.join(timeout=5.0)
            self._engine = None

        self._running = False
        if self._sel_a is None:
            self._top_status.configure(text="⚠ CAM A es obligatoria", text_color=GUI_YELLOW)
            if hasattr(self, '_apply_btn'):
                self._apply_btn.configure(state="normal", text="⟳  APLICAR CÁMARAS")
            return
        global INFER_EVERY
        try: INFER_EVERY = max(1, int(self._infer_entry.get()))
        except: pass

        print(f"[GUI] APLICAR: sel_a={self._sel_a}(cenital) sel_b={self._sel_b}(lat1) sel_c={self._sel_c}(lat2)")
        self._top_status.configure(
            text=f"Cargando YOLO + abriendo cenital={self._sel_a} lat1={self._sel_b} lat2={self._sel_c}...",
            text_color=GUI_GRAY)
        self.update()
        # Camera role mapping:
        #   sel_a = Cámara A (cenital/overhead) → engine cam_c (biomecánica overhead)
        #   sel_b = Cámara B (lateral 1)        → engine cam_a (detección principal + Kalman)
        #   sel_c = Cámara C (lateral 2)        → engine cam_b (referencia depth/estéreo)
        self._engine = VisionEngine(self._sel_b, self._sel_c, self._sel_a, DEFAULT_BASELINE)
        self._engine.start()
        self._running = True
        self._update_cam_titles()          # actualiza encabezados con índice/nombre/fps
        self.after(16, self._update_gui)
        # Re-enable button after startup time (YOLO load + camera warmup ~10s)
        self.after(12000, lambda: (
            self._apply_btn.configure(state="normal", text="⟳  APLICAR CÁMARAS")
            if hasattr(self, '_apply_btn') else None))

    def _update_cam_titles(self):
        """Actualiza los encabezados de las 3 vistas con el índice y nombre real del dispositivo.
        Muestra la RESOLUCIÓN OBJETIVO (1920×1080) y el FPS OBJETIVO (detectado por nombre de modelo),
        no los valores del probe que reflejan la resolución nativa sin configurar del driver.
        """
        cam_map = {c['index']: c for c in ALL_CAMERAS}
        roles   = ["CENITAL TOP", "IA + KALMAN", "DEPTH REF"]
        letters = ["A", "B", "C"]
        slots   = [self._sel_a, self._sel_b, self._sel_c]
        colors  = [GUI_GREEN, GUI_MAGENTA, GUI_CYAN]
        for i, (idx, role, letter, color) in enumerate(zip(slots, roles, letters, colors)):
            if idx is not None and idx in cam_map:
                c    = cam_map[idx]
                name = c.get('name', f'Cámara {idx}')
                # Detectar FPS objetivo por nombre de modelo (misma lógica que fps_of() en el engine)
                name_l = name.lower()
                if 'razer' in name_l or 'kiyo' in name_l:
                    target_fps = 60
                elif 'c920' in name_l or 'logitech' in name_l:
                    target_fps = 30
                else:
                    probe_fps = c.get('fps', 0)
                    target_fps = 60 if probe_fps >= 55 else (int(probe_fps) if probe_fps > 0 else 60)
                self._cam_title_lbls[i].configure(
                    text=f"CAM {letter}  ·  {role}")
                self._cam_info_lbls[i].configure(
                    text=f"[{idx}] {name}   1920×1080  @  {target_fps}fps",
                    text_color=color)
            else:
                self._cam_title_lbls[i].configure(
                    text=f"CAM {letter}  ·  {role}")
                self._cam_info_lbls[i].configure(
                    text="— sin cámara —", text_color=GUI_GRAY)

    def _update_gui(self):
        if not self._running or self._engine is None: return
        fa, fb, fc = self._engine.get_frames()
        stats = self._engine.get_stats()
        logs  = self._engine.get_logs()
        for lbl, frame in zip(self._cam_lbls, [fa, fb, fc]):
            if frame is not None: self._set_frame(lbl, frame)
        if stats:
            rem = stats.get('rem', 0); m2, s2 = rem//60, rem%60
            self._timer_lbl.configure(text=f"{m2:02d}:{s2:02d}")
            self._round_lbl.configure(text=f"ROUND {stats.get('rnd',1)}")
            ph, st = stats.get('phase','IDLE'), stats.get('state','IDLE')
            ptxt = ("IDLE" if st=="IDLE" else "PAUSA" if st=="PAUSED"
                    else "EN VIVO" if ph=="ROUND" else "DESCANSO")
            pcol = (GUI_GRAY if st=="IDLE" else GUI_RED if st=="PAUSED"
                    else GUI_GREEN if ph=="ROUND" else GUI_YELLOW)
            self._phase_lbl.configure(text=ptxt, text_color=pcol)
            self._top_status.configure(text=stats.get('status_msg',''), text_color=GUI_GRAY)
            fps_val = stats.get('eng_fps', 0)
            fps_col = GUI_GREEN if fps_val>20 else (GUI_YELLOW if fps_val>12 else GUI_RED)
            self._fps_lbl.configure(text=f"{fps_val:.0f}fps", text_color=fps_col)
            trk = stats.get('tracking', False)
            self._trk_lbl.configure(text="TRK" if trk else "YLO",
                                    text_color=GUI_CYAN if trk else GUI_GREEN)
            is_test = stats.get('mode_tm', False)
            def upd(cards, data):
                for k, c in cards.items():
                    if k.startswith('_'): continue
                    c.set(data.get(k, '—'))
                stance = data.get('stance', '?')
                bx     = data.get('boxing_score', {})
                # ── Modo label ──────────────────────────────────────
                if is_test:
                    cards['_mode'].configure(
                        text="MODO PRUEBA  ·  Golpes + Agresividad (guantes blancos)",
                        text_color=GUI_CYAN)
                else:
                    cards['_mode'].configure(
                        text="MODO PELEA  ·  Agresividad + Evasión",
                        text_color=GUI_GRAY)
                # ── Línea de detalle inferior ───────────────────────
                if is_test:
                    pt     = data.get('ptypes', {})
                    combos = data.get('combo_count', 0)
                    pwr_pct = bx.get('power_pct', 0.0)
                    bal = data.get('punch_balance', 0.0)
                    kc  = data.get('kinetic_chain', 0.0)
                    cards['_tl'].configure(
                        text=(f"J:{pt.get('JAB',0)} C:{pt.get('CROSS',0)} "
                              f"H:{pt.get('HOOK',0)} U:{pt.get('UPPERCUT',0)} "
                              f"O:{pt.get('OVERHAND',0)} B:{pt.get('BODYSHOT',0)}  "
                              f"| Combos:{combos}  Poder:{pwr_pct:.0f}%  [{stance}]  "
                              f"Bal:{bal:.2f}  KC:{kc:.2f}"))
                else:
                    aggr_sc = bx.get('aggr_score', 0.0)
                    evad_sc = bx.get('evasion_score', 0.0)
                    cards['_tl'].configure(
                        text=(f"Agresividad: {data.get('aggression',0)}  "
                              f"(sc {aggr_sc:.1f})  |  "
                              f"Evasiones: {data.get('dodges',0)}  Ágil: {data.get('agility',0.0):.1f}  "
                              f"(sc {evad_sc:.1f})  |  Postura: [{stance}]"))
                # ── Glove indicator ─────────────────────────────────
                glove_ok = data.get('glove_ok', False)
                if glove_ok:
                    cards['_glove'].configure(text="🥊 GUANTES OK", text_color=GUI_GREEN)
                else:
                    cards['_glove'].configure(text="⚠ SIN GUANTES", text_color=GUI_ORANGE)
            upd(self._rc, stats.get('red', {}))
            upd(self._bc, stats.get('blue', {}))
            rw = stats.get('rnd_winners', {})
            for i, badge in enumerate(self._round_badges):
                w = rw.get(i+1)
                if   w=="red":  badge.configure(fg_color=GUI_RED,  text_color=GUI_WHITE)
                elif w=="blue": badge.configure(fg_color=GUI_BLUE, text_color=GUI_WHITE)
                elif w=="test": badge.configure(fg_color=GUI_CYAN, text_color=GUI_BG)
                elif w=="draw": badge.configure(fg_color=GUI_GRAY, text_color=GUI_WHITE)
                else:           badge.configure(fg_color=GUI_CARD, text_color=GUI_GRAY)
            n3, nt = stats.get('n_3d',0), max(stats.get('n_kp',1),1)
            self._stereo_lbl.configure(text=f"3D: {n3}/{nt}",
                                       text_color=GUI_GREEN if n3>0 else GUI_GRAY)
            self._status_lbl.configure(text=stats.get('status_msg',''))
            # [10] Telemetry
            telem = stats.get('telem', {})
            self._telem_panel.update_telem(telem)
        if logs:
            self._log_box.configure(state="normal")
            self._log_box.delete("1.0", "end")
            for msg in logs[-14:]: self._log_box.insert("end", msg+"\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(16, self._update_gui)   # ~60fps display

    @staticmethod
    def _set_frame(lbl, bgr):
        try:
            lw=lbl.winfo_width(); lh=lbl.winfo_height()
            if lw < 10 or lh < 10: lw, lh = 426, 320
            asp = bgr.shape[1] / bgr.shape[0]
            if lw/lh > asp: lw = int(lh*asp)
            else:            lh = int(lw/asp)
            resized = cv2.resize(bgr, (lw,lh), interpolation=cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(lw,lh))
            lbl.configure(image=img, text=""); lbl._image = img
        except: pass

    def _cmd_quick_test(self):
        """Un clic: modo test con un solo peleador, sin guantes requeridos."""
        if not self._engine:
            self._top_status.configure(text="⚠ Aplica cámaras primero", text_color=GUI_YELLOW); return
        self._engine.cmd_start_test()
        self._top_status.configure(text="🧪 TEST RÁPIDO iniciado", text_color=GUI_CYAN)

    def _cmd_oficial(self):
        """Abre el diálogo de sesión oficial con carga de perfiles desde Supabase."""
        if not self._engine:
            self._top_status.configure(text="⚠ Aplica cámaras primero", text_color=GUI_YELLOW); return
        OfficialSessionDialog(self, self._engine)

    def _cmd_start(self):
        if not self._engine:
            self._top_status.configure(text="⚠ Aplica cámaras primero", text_color=GUI_YELLOW); return
        if not self._engine.cmd_start():
            msg = self._engine._status_msg or "⚠ Asigna roles y verifica guantes"
            self._top_status.configure(text=msg, text_color=GUI_ORANGE)

    def _cmd_pause(self):
        if self._engine: self._engine.cmd_pause()

    def _cmd_end(self):
        if self._engine: self._engine.cmd_end_round()

    def _cmd_end_session(self):
        if self._engine: self._engine.cmd_end_session()

    def _cmd_test(self):
        if self._engine: self._engine.cmd_force_test()

    def _cmd_red(self):
        if self._engine: self._engine.cmd_force_red()

    def _cmd_blue(self):
        if self._engine: self._engine.cmd_force_blue()

    def _cmd_clear(self):
        if self._engine: self._engine.cmd_clear()

    def _cmd_calib(self):
        if not self._engine:
            self._top_status.configure(text="⚠ Aplica cámaras primero", text_color=GUI_YELLOW); return
        CalibDialog(self, self._engine)

    def _cmd_dataset_toggle(self):
        global DATASET_ENABLED
        DATASET_ENABLED = not DATASET_ENABLED
        col = GUI_GREEN if DATASET_ENABLED else GUI_GRAY
        txt = f"💾  DATASET: {'ON' if DATASET_ENABLED else 'OFF'}"
        self._dataset_btn.configure(text=txt, text_color=col, border_color=col)

    def _cmd_api_toggle(self):
        global API_ENABLED
        API_ENABLED = not API_ENABLED
        col = GUI_GREEN if API_ENABLED else GUI_GRAY
        txt = f"🌐  API: {'ON' if API_ENABLED else 'OFF'}"
        self._api_btn.configure(text=txt, text_color=col, border_color=col)

    def _cmd_apply_baseline(self):
        if not self._engine: return
        try:
            bl = float(self._bl_entry.get())
            with self._engine._lock:
                self._engine.stereo_ab.B = max(0.05, bl)
                self._engine.stereo_ac.B = max(0.05, bl * 1.2)
            self._engine._log(f"Baseline → {bl:.2f}m")
        except Exception as e:
            print(f"[baseline] {e}")

    # ── Live Stream controls ───────────────────────────────────────────────────

    def _cmd_live_toggle(self):
        global LIVE_STREAM_ENABLED
        if not self._engine:
            self._top_status.configure(
                text="⚠ Aplica cámaras antes de activar EN VIVO", text_color=GUI_YELLOW)
            return

        if self._live and self._live.is_alive():
            # ── DETENER ────────────────────────────────────────────
            self._live.stop()
            VSTRM.stop()
            self._live = None
            LIVE_STREAM_ENABLED = False
            self._live_btn.configure(text="🔴  EN VIVO: OFF",
                                     fg_color="#1a0808", text_color=GUI_RED,
                                     border_color="#602020")
            self._log_entry("Stream en vivo detenido")
        else:
            # ── INICIAR ────────────────────────────────────────────
            if not SUPABASE_URL or not SUPABASE_ANON_KEY:
                self._cmd_live_config()   # abrir configuración primero
                return
            self._live = LiveStreamManager(self._engine)
            self._live.start()
            LIVE_STREAM_ENABLED = True
            # Iniciar RTMP solo si hay URL configurada
            if STREAM_RTMP_URL:
                ok, msg = VSTRM.start(STREAM_RTMP_URL, STREAM_FPS_TARGET)
                self._log_entry(f"RTMP: {msg}")
            self._live_btn.configure(text="🔴  EN VIVO: ON",
                                     fg_color="#1a0000", text_color="#ff4040",
                                     border_color="#ff2020")
            self._log_entry(f"Stream iniciado · sesión {self._live.session_id}")

    def _cmd_live_config(self):
        """Abre el diálogo de configuración de Supabase + RTMP."""
        _StreamConfigDialog(self)

    def _refresh_live_status(self):
        """Actualiza el label de estado de Supabase/RTMP cada 3 segundos."""
        try:
            supa_txt = f"OK:{SUPA.push_ok} ERR:{SUPA.push_err}"
            rtmp_txt = "ON" if VSTRM.is_running else "—"
            self._live_stat_lbl.configure(
                text=f"Supabase: {supa_txt}  |  RTMP: {rtmp_txt}",
                text_color=GUI_GREEN if SUPA.push_ok > 0 and SUPA.push_err == 0
                           else (GUI_YELLOW if SUPA.push_ok > 0 else GUI_GRAY))
        except Exception: pass
        self.after(3000, self._refresh_live_status)

    def _log_entry(self, msg: str):
        """Añade entrada al log de la GUI."""
        if hasattr(self, '_log_box'):
            self._log_box.configure(state="normal")
            self._log_box.insert("end", f"[live] {msg}\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

    def _on_close(self):
        self._running = False
        if self._live:
            self._live.stop(); VSTRM.stop()
        if self._engine: self._engine.cmd_stop()
        DATASET.stop_session()
        time.sleep(0.3); self.destroy()

# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = FighterIDApp()
    app.mainloop()