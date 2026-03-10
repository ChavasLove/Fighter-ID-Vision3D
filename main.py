"""
FighterID Vision v4.0  –  3-Camera · GPU AMD · Hardened Pipeline
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
import os, subprocess, json, requests, csv, pathlib
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
            print(f"[GPU] CUDA: {torch.cuda.get_device_name(0)}")
        else:
            print("[CPU] sin GPU acelerada")
    except ImportError:
        print("[CPU] torch no disponible")
try:
    import torch
    torch.set_num_threads(4)
except ImportError:
    pass
cv2.setNumThreads(4)
cv2.ocl.setUseOpenCL(False)

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
ROUND_TIME       = 180;  REST_TIME        = 60;   TOTAL_ROUNDS     = 3
INFER_IMGSZ      = 320;  INFER_EVERY      = 6;    INFER_CONF       = 0.40
VOTE_WINDOW      = 30;   VOTE_NEEDED      = 10
PUNCH_SPD_THR_MS = 0.55; PUNCH_SPD_CAP_MS = 25.0
EXTENSION_THR_M  = 0.14; RETRACTION_RATIO = 0.58
MIN_PUNCH_DUR    = 0.05; MAX_PUNCH_DUR    = 0.70
HIT_R_M          = 0.30; HEAD_HIT_R_M     = 0.20
BODY_HIT_R_M     = 0.35
DODGE_SPD_MS     = 0.40; HISTORY_LEN      = 20
CAM_W, CAM_H     = 1920, 1080
FOCAL_EST        = CAM_W * 0.8
CX, CY           = CAM_W / 2, CAM_H / 2
MAX_CAMS         = 10
DEFAULT_BASELINE = 1.50

# FighterID Platform API
FIGHTERID_API_URL = "https://api.fighterid.io/ai-strike-ingest/event"
FIGHTERID_API_KEY = ""   # set your API key here
API_ENABLED       = False

# Dataset capture
DATASET_DIR = pathlib.Path("dataset_capture")
DATASET_ENABLED = False

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

# GUI hex
GUI_BG      = "#0d0d12"; GUI_PANEL   = "#13131a"; GUI_CARD    = "#1a1a24"
GUI_BORDER  = "#2a2a3a"; GUI_RED     = "#e03030"; GUI_BLUE    = "#2080ff"
GUI_CYAN    = "#00e5e5"; GUI_GREEN   = "#30e060"; GUI_YELLOW  = "#e0c020"
GUI_MAGENTA = "#cc30cc"; GUI_WHITE   = "#e8e8f0"; GUI_GRAY    = "#505060"
GUI_ORANGE  = "#ff8c00"; GUI_BLACK   = "#08080c"

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
            timeout=6, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore").strip()
        if out:
            data = json.loads(out)
            return [data] if isinstance(data, str) else list(data)
    except: pass
    return []

def _probe_camera(idx, target_w=1920, target_h=1080):
    for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
        cap = None
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened(): cap.release(); continue
            cap.read(); time.sleep(0.05)
            try: cap.set(cv2.CAP_PROP_FRAME_WIDTH,  target_w)
            except: pass
            try: cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            except: pass
            try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except: pass
            for _ in range(3): cap.read()
            ok, frame = cap.read()
            if not ok or frame is None: cap.release(); continue
            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0 or fps > 240:
                t0 = time.time()
                for _ in range(8): cap.read()
                fps = round(8 / max(time.time() - t0, 0.001), 1)
            cap.release()
            return {'w': w, 'h': h, 'fps': fps}
        except Exception as e:
            print(f"  [probe] idx={idx}: {e}")
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
    print(f"\nEscaneando cámaras 0..{MAX_CAMS-1}  (Camo/1080p mode)…")
    candidates = []
    for i in range(MAX_CAMS):
        info = _probe_camera(i)
        if info is None: continue
        name = dev_names[i] if i < len(dev_names) else f"Camara {i}"
        info.update({'index': i, 'name': name}); candidates.append(info)
        print(f"  [PROBE] [{i}] {name}  {info['w']}x{info['h']}@{info['fps']:.0f}fps")
    groups: dict = {}
    for c in candidates: groups.setdefault(c['name'], []).append(c)
    selected = []
    for name, cams in groups.items():
        best    = max(cams, key=_res_score)
        skipped = [c['index'] for c in cams if c['index'] != best['index']]
        selected.append(best)
        if skipped:
            print(f"  [CAMO]  '{name}': usando idx={best['index']} "
                  f"({best['w']}x{best['h']}), descartados={skipped}")
    name_count: dict = {}; found = []
    for c in sorted(selected, key=lambda x: x['index']):
        base = c['name']; name_count[base] = name_count.get(base, 0) + 1
        label = (f"[{c['index']}] {base}  {c['w']}x{c['h']}@{c['fps']:.0f}fps"
                 if name_count[base] == 1 else
                 f"[{c['index']}] {base} #{name_count[base]}  {c['w']}x{c['h']}@{c['fps']:.0f}fps")
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
                dev = 0 if _DEVICE == "dml" else _DEVICE
                r = self.model(f, imgsz=INFER_IMGSZ, conf=INFER_CONF, verbose=False, device=dev)
                if _cpu_fallback:
                    print(f"[{self.name}] GPU recovered"); _cpu_fallback = False
                with self._lk: self._rout = r
            except Exception as e_gpu:
                if not _cpu_fallback:
                    print(f"[{self.name}] GPU failed ({e_gpu}), falling back to CPU")
                    _cpu_fallback = True
                try:
                    r = self.model(f, imgsz=INFER_IMGSZ, conf=INFER_CONF, verbose=False, device="cpu")
                    with self._lk: self._rout = r
                except Exception as e2:
                    print(f"[{self.name}] CPU also failed: {e2}")
            self.last_latency_ms = (time.perf_counter() - t0) * 1000
            self.total_infers += 1

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
class FighterIDAPI:
    def __init__(self):
        self._queue: deque = deque(maxlen=500)
        self._thread = threading.Thread(target=self._worker, daemon=True, name="APIExport")
        self._thread.start()
        self.sent_ok  = 0
        self.sent_err = 0

    def _worker(self):
        while True:
            if not self._queue:
                time.sleep(0.05); continue
            evt = self._queue.popleft()
            if not API_ENABLED or not FIGHTERID_API_KEY:
                continue
            try:
                r = requests.post(
                    FIGHTERID_API_URL,
                    json=evt,
                    headers={"Authorization": f"Bearer {FIGHTERID_API_KEY}",
                             "Content-Type": "application/json"},
                    timeout=3)
                if r.status_code == 200: self.sent_ok += 1
                else:                    self.sent_err += 1
            except Exception as e:
                self.sent_err += 1

    def send(self, fighter_id: str, punch_type: str, speed: float, extension: float,
             hit: bool, face_hit: bool, body_hit: bool, elbow_angle: float = 0.0):
        evt = {
            "fighter_id":  fighter_id,
            "punch_type":  punch_type.lower(),
            "speed":       round(speed, 3),
            "extension":   round(extension, 3),
            "hit":         hit,
            "face_hit":    face_hit,
            "body_hit":    body_hit,
            "elbow_angle": round(elbow_angle, 1),
            "timestamp":   time.time(),
        }
        self._queue.append(evt)

FAPI = FighterIDAPI()

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

    def reset(self):
        self.strikes = self.connected = self.aggr = self.face_hits = self.body_hits = 0
        self.max_spd_ms = self.max_ext_m = 0.0
        self.hL.clear(); self.hR.clear()
        self.pL = self.pR = self.pt = None
        self.punchL = self.punchR = False; self.tL = self.tR = self.mL = self.mR = 0.0
        self.ptypes = {"JAB":0,"CROSS":0,"HOOK":0,"UPPERCUT":0,"OVERHAND":0,"BODYSHOT":0}
        self.head.reset(); self._lfht = 0.0; self.spd_history.clear()

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
        Approximate shoulder rotation: lateral offset diff L vs R shoulder in X.
        Positive → counter-clockwise rotation (orthodox cross / southpaw jab).
        """
        p3 = self.pts3d
        ls, rs = p3.get(5), p3.get(6)
        if ls is None or rs is None: return 0.0
        return float(ls[0] - rs[0])

    def _hip_rotation(self) -> float:
        """Lateral offset diff L vs R hip."""
        p3 = self.pts3d
        lh, rh = p3.get(11), p3.get(12)
        if lh is None or rh is None: return 0.0
        return float(lh[0] - rh[0])

    def _classify(self, wp3, sp3, left, vel3, dur, mx) -> str:
        if sp3 is None: return "UNKNOWN"
        vx, vy, vz = vel3; spd = math.sqrt(vx*vx + vy*vy + vz*vz)
        if spd < 0.01: return "UNKNOWN"
        vyn   = vy / spd
        lat   = abs(vx) / (abs(vz) + 0.001)
        hdiff = sp3[1] - wp3[1]

        # Elbow angle at peak: bent = hook/uppercut, extended = jab/cross
        elbow = self._elbow_angle(left)
        sh_rot = self._shoulder_rotation()
        hip_rot = self._hip_rotation()

        # BODYSHOT: target below shoulder level
        if hdiff > 0.25 and wp3[1] > sp3[1] + 0.15:
            return "BODYSHOT"

        # UPPERCUT: upward trajectory, bent elbow
        if vyn < -0.4 and hdiff < 0.1 and (elbow < 120 or elbow == 0):
            return "UPPERCUT"

        # HOOK: lateral trajectory, bent elbow
        if lat > 0.8 and elbow < 140:
            return ("OVERHAND" if vyn > 0.2 and mx > EXTENSION_THR_M*1.8 and dur > 0.18
                    else "HOOK")

        # JAB / CROSS: straight punch, extended elbow
        if left:
            if lat < 1.5 and dur < 0.25 and mx > EXTENSION_THR_M*1.5:
                return "JAB"
        else:
            if lat < 1.5 and mx > EXTENSION_THR_M*1.6:
                return "CROSS"

        # Fallback based on rotation
        if abs(sh_rot) > 0.05 or abs(hip_rot) > 0.05:
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
            rec=list(hist); sw=[]
            for a,b in ((rec[-3],rec[-2]),(rec[-2],rec[-1])):
                dtw = b['time'] - a['time']
                if dtw > 0.001: sw.append(dist3d(b['pos3d'],a['pos3d'])/dtw)
            if sw: spd = float(np.mean(sw))
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
                peak_ok   = cur > EXTENSION_THR_M * 1.3
                if retracted and slow and dur_ok and peak_ok:
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
                    ptype = self._classify(wp3, sp3, left, av3, dur, cur)
                    if ptype in self.ptypes: self.ptypes[ptype] += 1
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
    def __init__(self):
        self._wins = {}; self.locked = False
        self.test_pid = self.red_pid = self.blue_pid = None; self.mode = "none"

    def _ensure(self, pid):
        if pid not in self._wins:
            self._wins[pid] = {'W': deque(maxlen=VOTE_WINDOW),
                               'R': deque(maxlen=VOTE_WINDOW),
                               'B': deque(maxlen=VOTE_WINDOW)}

    def update(self, pid, w_ok, r_ok, b_ok):
        if self.locked: return
        self._ensure(pid); d = self._wins[pid]
        d['W'].append(w_ok); d['R'].append(r_ok); d['B'].append(b_ok)

    def try_confirm(self):
        if self.locked: return False
        for pid, d in self._wins.items():
            if pid in (self.test_pid, self.red_pid, self.blue_pid): continue
            wc=sum(d['W']); rc=sum(d['R']); bc=sum(d['B'])
            if wc>=VOTE_NEEDED and wc>=rc and wc>=bc:
                if self.mode == "none":
                    self.test_pid=pid; self.mode="test"; self.locked=True; return True
            if rc>=VOTE_NEEDED and self.red_pid is None and self.mode!="test":
                self.red_pid=pid; self.mode="fight"
            if bc>=VOTE_NEEDED and self.blue_pid is None and self.mode!="test":
                self.blue_pid=pid; self.mode="fight"
        if self.red_pid and self.blue_pid: self.locked = True
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
        self._frame_a = self._frame_b = self._frame_c = None
        self._stats = {}; self._pids = []
        self._status_msg = "Muestra guantes + torso  |  asigna roles"
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
        if f.strikes == 0: return 0.0
        return f.connected/max(1,f.strikes)*100 + f.aggr*0.2 + f.max_spd_ms*2

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
            gi = {'white': cL.get('white',False) or cR.get('white',False),
                  'red':   cL.get('red',  False) or cR.get('red',  False),
                  'blue':  cL.get('blue', False) or cR.get('blue', False),
                  'bare':  bare_torso(frame, kp)}
            persons.append((idx+pid_offset, kp, cf, gi))
        return persons

    def _process_cam(self, frame, res, pid_offset=0):
        parsed = self._parse_result(res)
        kps = [kp for kp, _ in parsed]; cfs = [cf for _, cf in parsed]
        return self._process_cam_kp(frame, kps, cfs, pid_offset)

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock: self._log_msgs.append(f"[{ts}] {msg}")

    def _end_round(self):
        sc = self._score(self.red)
        if self.tm:
            acc = self.red.connected/max(1,self.red.strikes)*100
            self.rnd_stats[self.rnd] = {
                "mode":"test","strikes":self.red.strikes,
                "connected":self.red.connected,"max_speed_ms":self.red.max_spd_ms,
                "max_ext_m":self.red.max_ext_m,"score":sc,
                "punch_types":self.red.ptypes.copy(),"accuracy":round(acc,1)}
            self.rnd_winners[self.rnd] = "test"; self._reset_ts()
            self._log(f"Round {self.rnd}: TEST — {self.red.strikes} golpes, {acc:.1f}%")
        else:
            rs=self._score(self.red); bs=self._score(self.blue)
            w="draw" if rs==bs else ("red" if rs>bs else "blue")
            self.rnd_winners[self.rnd] = w
            self.rnd_stats[self.rnd] = {
                "winner":w,"red_score":rs,"blue_score":bs,
                "red":{"strikes":self.red.strikes,"connected":self.red.connected,
                       "face_hits":self.red.face_hits,"body_hits":self.red.body_hits,
                       "max_speed_ms":self.red.max_spd_ms,"dodges":self.red.head.dodges,
                       "punch_types":self.red.ptypes.copy()},
                "blue":{"strikes":self.blue.strikes,"connected":self.blue.connected,
                        "face_hits":self.blue.face_hits,"body_hits":self.blue.body_hits,
                        "max_speed_ms":self.blue.max_spd_ms,"dodges":self.blue.head.dodges,
                        "punch_types":self.blue.ptypes.copy()}}
            self._log(f"Round {self.rnd}: ganador {w.upper()}")

    def cmd_start(self):
        if not self.roles.ready: return False
        self.session_state="RUNNING"; self.phase="ROUND"
        self.rnd=1; self.rnd_done=0
        self.t_start=time.time(); self.t_paused=0.0; self.t_pause=0.0
        self.red.reset(); self.blue.reset()
        self.rnd_stats={}; self.rnd_winners={}; self._reset_ts()
        if DATASET_ENABLED: DATASET.start_session()
        self._log("=== SESIÓN INICIADA ==="); return True

    def cmd_pause(self):
        if self.session_state=="RUNNING":
            self.session_state="PAUSED"; self.t_pause=time.time(); self._log("Pausa")
        elif self.session_state=="PAUSED":
            self.t_paused += time.time()-self.t_pause
            self.session_state="RUNNING"; self._log("Resume")

    def cmd_end_round(self):
        if self.session_state in ("RUNNING","PAUSED") and self.phase=="ROUND":
            self._end_round(); self.rnd_done+=1

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

    def run(self):
        def open_cap(idx, fps=30):
            for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
                cap = None
                try:
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened(): cap.release(); continue
                    cap.read(); time.sleep(0.05)
                    try: cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
                    except: pass
                    try: cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
                    except: pass
                    try: cap.set(cv2.CAP_PROP_FPS, fps)
                    except: pass
                    try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except: pass
                    return cap
                except Exception as e:
                    print(f"  [open_cap] idx={idx} backend={backend}: {e}")
                    if cap:
                        try: cap.release()
                        except: pass
            return cv2.VideoCapture(idx)

        def fps_of(idx, default=30):
            for c in ALL_CAMERAS:
                if c['index'] == idx: return min(c['fps'], 60)
            return default

        self._log(f"Cargando YOLO pose (device={_DEVICE})...")
        model = YOLO("yolov8n-pose.pt")

        # [1] THREE independent inference threads
        inf_a = InferThread(model, "InferA")
        inf_b = InferThread(model, "InferB")
        inf_c = InferThread(model, "InferC")
        inf_a.start(); inf_b.start(); inf_c.start()

        cap_a = open_cap(self.cam_a_idx, fps_of(self.cam_a_idx, 60))
        cap_b = (open_cap(self.cam_b_idx, fps_of(self.cam_b_idx, 60))
                 if self.cam_b_idx is not None else None)
        cap_c = (open_cap(self.cam_c_idx, fps_of(self.cam_c_idx, 30))
                 if self.cam_c_idx is not None else None)

        if not cap_a.isOpened():
            self._log(f"ERROR: no se pudo abrir CAM A (idx={self.cam_a_idx})")
            inf_a.stop(); inf_b.stop(); inf_c.stop(); return

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

        self._log("Calentando cámaras...")
        for _ in range(3):
            cap_a.read()
            if cap_b: cap_b.read()
            if cap_c: cap_c.read()
            time.sleep(0.03)

        last_a = last_b = last_c = None
        fc = 0; fc_c = 0; frame_c_cached = None
        use_tracking = False
        _scale  = CAM_W / 640
        GLOVE_R = max(8,  int(8  * _scale))
        HEAD_R  = max(12, int(16 * _scale))

        self._log(f"v4.0 listo ✓  GPU={_DEVICE.upper()}  scipy={'YES' if _HAS_SCIPY else 'NO'} "
                  f"INFER={INFER_EVERY}  RES={CAM_W}x{CAM_H}")

        while self._go:
            ret_a, frame_a = cap_a.read()
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
            if cap_b:
                ret_b, fb = cap_b.read()
                if ret_b and fb is not None: frame_b = cv2.flip(fb, 1)
            frame_c = None
            if cap_c:
                fc_c += 1
                if fc_c % 2 == 0:
                    ret_c, fr = cap_c.read()
                    if ret_c and fr is not None: frame_c_cached = cv2.flip(fr, 1)
                frame_c = frame_c_cached

            fc += 1; ct = time.time()
            self._fps_counter.append(ct)
            gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)

            # [1] Submit all cameras to their independent inference threads
            if fc % INFER_EVERY == 0:
                inf_a.submit(frame_a)
                if frame_b is not None: inf_b.submit(frame_b)
                if frame_c is not None: inf_c.submit(frame_c)
                use_tracking = False
            else:
                use_tracking = True

            r_a = inf_a.result()
            r_b = inf_b.result()
            r_c = inf_c.result()
            if r_a is not None: last_a = r_a
            if r_b is not None: last_b = r_b
            if r_c is not None: last_c = r_c

            # Kalman-smoothed keypoints via pose tracker
            if r_a is not None:
                parsed = self._parse_result(r_a)
                if parsed:
                    kp_list = [kp for kp, _ in parsed]
                    cf_list = [cf for _, cf in parsed]
                    self._pose_tracker.update_from_yolo(gray_a, kp_list, cf_list)
                    current_kp_list = kp_list
                    current_cf_list = cf_list
                else:
                    current_kp_list = current_cf_list = []
            elif use_tracking:
                current_kp_list, current_cf_list = self._pose_tracker.track(gray_a)
            else:
                current_kp_list = current_cf_list = []

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

            fused_data = {}; n_3d = n_total = 0
            for i_a, (pid_a, kp_a, cf_a, gi_a) in enumerate(persons_a):
                match_b_entry = b_lookup.get(i_a)
                match_c_entry = c_lookup.get(i_a)
                if match_b_entry:
                    _, kp_b, cf_b, _ = match_b_entry
                    fused_kp, pts3d, origin = self.stereo_ab.fuse_keypoints(kp_a, kp_b, cf_a, cf_b)
                    n_3d += sum(1 for o in origin.values() if o=='AB')
                    if match_c_entry:
                        _, kp_c, cf_c, _ = match_c_entry
                        _, pts3d_c, orig_c = self.stereo_ac.fuse_keypoints(kp_a, kp_c, cf_a, cf_c)
                        for ki in pts3d:
                            if ki in pts3d_c and orig_c.get(ki)=='AB':
                                pts3d[ki] = tuple((np.array(pts3d[ki])+np.array(pts3d_c[ki]))/2)
                                origin[ki] = 'ABC'
                else:
                    pts3d  = {i: self.stereo_ab.depth_from_single(kp_a[i][0],kp_a[i][1])
                              for i in range(min(17,len(kp_a)))
                              if not(kp_a[i][0]==0 and kp_a[i][1]==0)}
                    fused_kp = kp_a; origin = {i:'A' for i in pts3d}
                fused_data[pid_a] = {'fused_kp':fused_kp,'pts3d':pts3d,'origin':origin}
                n_total += len(origin)

            new_pos3d = {}
            for pid, fd in fused_data.items():
                tc3 = torso_center_3d(fd['pts3d'])
                if tc3: new_pos3d[pid] = tc3
            if new_pos3d: self.opp_pos3d = new_pos3d

            self._pids = [pid for pid,_,_,_ in persons_a]
            for pid_a, kp_a, cf_a, gi_a in persons_a:
                bare = gi_a.get('bare', False)
                self.roles.update(pid_a,
                    w_ok=gi_a.get('white',False) and bare,
                    r_ok=gi_a.get('red',  False) and bare,
                    b_ok=gi_a.get('blue', False) and bare)
            self.roles.try_confirm()

            if self.roles.mode == "test":
                self._status_msg = "MODO TEST — Presiona INICIAR"
            elif self.roles.mode == "fight" and self.roles.red_pid and self.roles.blue_pid:
                self._status_msg = "LUCHA LISTA — Presiona INICIAR"
            elif self.roles.red_pid:
                self._status_msg = "Esperando esquina AZUL…"
            elif self.roles.blue_pid:
                self._status_msg = "Esperando esquina ROJA…"
            else:
                self._status_msg = "Muestra guantes + torso  |  asigna roles"

            can_det = self.session_state=="RUNNING" and self.phase=="ROUND"
            rp=self.roles.red_pid; bp=self.roles.blue_pid; tp=self.roles.test_pid

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                fd       = fused_data.get(pid_a, {})
                pts3d    = fd.get('pts3d', {})
                origin   = fd.get('origin', {})
                fused_kp = fd.get('fused_kp', kp_a)
                ftr = None; rcol = GRY; rlbl = "?"
                if pid_a == rp:   ftr=self.red;  rcol=RED; rlbl="RED"
                elif pid_a == bp: ftr=self.blue; rcol=BLU; rlbl="BLU"
                elif pid_a == tp: ftr=self.red;  rcol=WHT; rlbl="TEST"

                # Pass 3D keypoints to fighter for biomechanical analysis
                if ftr: ftr.pts3d = pts3d

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
                            if DATASET_ENABLED: DATASET.stop_session()
                            self.session_state="IDLE"; self.phase="IDLE"
                        else:
                            self.phase="REST"; self.t_start=time.time()
                else:
                    rem = max(0, int(REST_TIME - el))
                    if rem == 0:
                        self.rnd += 1; self.phase="ROUND"
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
            hud(img_a, f"CAM A · {eng_fps:.0f}fps · 3D:{n_3d}/{max(n_total,1)} · {trk_tag} · KAL", GRN)
            hud(img_b, f"CAM B · DEPTH REF · lat={inf_b.last_latency_ms:.0f}ms", MAG)
            hud(img_c, f"CAM C · BROADCAST · lat={inf_c.last_latency_ms:.0f}ms", CYN)

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
                    'score':round(self._score(self.red),1),'ptypes':dict(self.red.ptypes),
                },
                'blue':{
                    'strikes':self.blue.strikes,'connected':self.blue.connected,
                    'face_hits':self.blue.face_hits,'body_hits':self.blue.body_hits,
                    'accuracy':self.blue.accuracy(),
                    'max_spd':round(self.blue.max_spd_ms,2),'max_ext':round(self.blue.max_ext_m,2),
                    'agility':self.blue.head.agility(),'dodges':self.blue.head.dodges,
                    'score':round(self._score(self.blue),1),'ptypes':dict(self.blue.ptypes),
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
        cap_a.release()
        if cap_b: cap_b.release()
        if cap_c: cap_c.release()

# ══════════════════════════════════════════════════════════════════
#  STAT CARD
# ══════════════════════════════════════════════════════════════════
class StatCard(ctk.CTkFrame):
    def __init__(self, parent, label, value="—", unit="", accent=GUI_CYAN, **kw):
        super().__init__(parent, fg_color=GUI_CARD, corner_radius=8, **kw)
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=9,weight="bold"),
                     text_color=GUI_GRAY).pack(anchor="w", padx=8, pady=(6,0))
        self._val = ctk.CTkLabel(self, text=value,
                                 font=ctk.CTkFont("Courier New",18,weight="bold"),
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
        self.title("FighterID Vision v4.0  —  3-Camera · Kalman · Hungarian · Biomech")
        self.configure(fg_color=GUI_BG)
        sw=self.winfo_screenwidth(); sh=self.winfo_screenheight()
        self.geometry(f"{min(sw,1440)}x{min(sh,920)}+0+0")
        self._engine: VisionEngine = None
        self._running = False
        self._sel_a = self._sel_b = self._sel_c = None
        self._build_ui()
        self.after(300, self._init_cameras)

    def _build_ui(self):
        top = ctk.CTkFrame(self, height=52, fg_color=GUI_PANEL, corner_radius=0)
        top.pack(fill="x", side="top"); top.pack_propagate(False)
        ctk.CTkLabel(top, text="⬡  FIGHTER ID  v4.0",
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
        lbl("CÁMARA A  (IA)")
        self._cb_a = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_GREEN,
                                     button_color=GUI_GREEN, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('A',v))
        self._cb_a.pack(fill="x", padx=12, pady=2)
        lbl("CÁMARA B  (depth)")
        self._cb_b = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_MAGENTA,
                                     button_color=GUI_MAGENTA, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('B',v))
        self._cb_b.pack(fill="x", padx=12, pady=2)
        lbl("CÁMARA C  (broadcast)")
        self._cb_c = ctk.CTkComboBox(parent, values=["— escanear —"],
                                     fg_color=GUI_CARD, border_color=GUI_CYAN,
                                     button_color=GUI_CYAN, text_color=GUI_WHITE,
                                     font=ctk.CTkFont(size=9), height=28,
                                     command=lambda v: self._on_cam_select('C',v))
        self._cb_c.pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⟳  APLICAR CÁMARAS", fg_color=GUI_PANEL,
                      text_color=GUI_CYAN, border_color=GUI_CYAN, border_width=1,
                      hover_color=GUI_CARD, command=self._cmd_apply_cams,
                      corner_radius=7, height=30,
                      font=ctk.CTkFont(size=10,weight="bold")).pack(fill="x", padx=12, pady=4)
        sep(); lbl("SESIÓN")
        ctk.CTkButton(parent, text="▶  INICIAR", fg_color=GUI_GREEN,
                      text_color=GUI_BG, hover_color="#28b84e",
                      command=self._cmd_start, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⏸  PAUSA", fg_color=GUI_YELLOW,
                      text_color=GUI_BG, hover_color="#c0a010",
                      command=self._cmd_pause, **B).pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="⏹  FIN ROUND", fg_color=GUI_RED,
                      text_color=GUI_WHITE, hover_color="#b02020",
                      command=self._cmd_end, **B).pack(fill="x", padx=12, pady=2)
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
        sep(); lbl("REGISTRO")
        self._log_box = ctk.CTkTextbox(parent, fg_color=GUI_CARD, text_color=GUI_GRAY,
                                       font=ctk.CTkFont("Courier New",8),
                                       wrap="word", corner_radius=6)
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0,12))

    def _build_center(self, parent):
        cam_row = ctk.CTkFrame(parent, fg_color="transparent")
        cam_row.pack(fill="both", expand=True, padx=4, pady=(4,2))
        self._cam_lbls = []
        for title, color in [
            ("CAM A  ·  IA + KALMAN", GUI_GREEN),
            ("CAM B  ·  DEPTH REF",   GUI_MAGENTA),
            ("CAM C  ·  BROADCAST",   GUI_CYAN),
        ]:
            f = ctk.CTkFrame(cam_row, fg_color=GUI_CARD, corner_radius=10)
            f.pack(side="left", fill="both", expand=True, padx=3)
            ctk.CTkLabel(f, text=title,
                         font=ctk.CTkFont(size=9,weight="bold"),
                         text_color=color).pack(pady=(6,2))
            lbl = ctk.CTkLabel(f, text="", fg_color=GUI_BLACK)
            lbl.pack(fill="both", expand=True, padx=4, pady=(0,4))
            self._cam_lbls.append(lbl)
        stats_bar = ctk.CTkFrame(parent, fg_color=GUI_PANEL, height=210, corner_radius=0)
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
        grid = ctk.CTkFrame(f, fg_color="transparent"); grid.pack(fill="x", padx=4)
        defs = [("strikes","GOLPES",""),("connected","HITS",""),
                ("accuracy","PREC","%"),("face_hits","CARA",""),
                ("body_hits","CUERPO",""),
                ("max_spd","VEL MÁX","m/s"),("max_ext","EXT","m"),
                ("agility","AGIL",""),("dodges","ESQV",""),("score","SCORE","")]
        cards = {}
        for i, (k, lb, unit) in enumerate(defs):
            c = StatCard(grid, lb, unit=unit, accent=color)
            c.grid(row=i//5, column=i%5, padx=2, pady=2, sticky="ew")
            grid.columnconfigure(i%5, weight=1); cards[k] = c
        tl = ctk.CTkLabel(f, text="", font=ctk.CTkFont("Courier New",9),
                           text_color=GUI_GRAY, justify="left")
        tl.pack(anchor="w", padx=10, pady=(2,4)); cards['_tl'] = tl
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
        if self._engine:
            self._engine.cmd_stop(); time.sleep(0.4); self._engine = None
        self._running = False
        if self._sel_a is None:
            self._top_status.configure(text="⚠ CAM A es obligatoria", text_color=GUI_YELLOW); return
        global INFER_EVERY
        try: INFER_EVERY = max(1, int(self._infer_entry.get()))
        except: pass
        self._top_status.configure(
            text=f"Iniciando v4.0: A={self._sel_a} B={self._sel_b} C={self._sel_c}",
            text_color=GUI_GRAY)
        self.update()
        self._engine = VisionEngine(self._sel_a, self._sel_b, self._sel_c, DEFAULT_BASELINE)
        self._engine.start()
        self._running = True
        self.after(50, self._update_gui)

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
            def upd(cards, data):
                for k, c in cards.items():
                    if k == '_tl': continue
                    c.set(data.get(k, '—'))
                pt = data.get('ptypes', {})
                cards['_tl'].configure(
                    text=(f"J:{pt.get('JAB',0)} C:{pt.get('CROSS',0)} "
                          f"H:{pt.get('HOOK',0)} U:{pt.get('UPPERCUT',0)} "
                          f"O:{pt.get('OVERHAND',0)} B:{pt.get('BODYSHOT',0)}"))
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
        self.after(50, self._update_gui)

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

    def _cmd_start(self):
        if not self._engine:
            self._top_status.configure(text="⚠ Aplica cámaras primero", text_color=GUI_YELLOW); return
        if not self._engine.cmd_start():
            self._top_status.configure(text="⚠ Asigna roles primero", text_color=GUI_YELLOW)

    def _cmd_pause(self):
        if self._engine: self._engine.cmd_pause()

    def _cmd_end(self):
        if self._engine: self._engine.cmd_end_round()

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

    def _on_close(self):
        self._running = False
        if self._engine: self._engine.cmd_stop()
        DATASET.stop_session()
        time.sleep(0.3); self.destroy()

# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = FighterIDApp()
    app.mainloop()