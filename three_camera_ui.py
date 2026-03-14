"""
FighterID Vision v3.2  –  3-Camera GUI Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
pip install customtkinter pillow ultralytics opencv-python numpy
"""

import os, subprocess
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"

import cv2, numpy as np, time, math, datetime, threading
from collections import deque
from ultralytics import YOLO
import customtkinter as ctk
from PIL import Image

try:
    import torch; torch.set_num_threads(6)
except ImportError:
    pass
cv2.setNumThreads(3)

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
ROUND_TIME        = 180;  REST_TIME         = 60;   TOTAL_ROUNDS      = 3
INFER_IMGSZ       = 384;  INFER_EVERY       = 2;    INFER_CONF        = 0.42
VOTE_WINDOW       = 30;   VOTE_NEEDED       = 10
PUNCH_SPD_THR_MS  = 0.55; PUNCH_SPD_CAP_MS  = 25.0
EXTENSION_THR_M   = 0.14; RETRACTION_RATIO  = 0.58
MIN_PUNCH_DUR     = 0.05; MAX_PUNCH_DUR     = 0.70
HIT_R_M           = 0.30; HEAD_HIT_R_M      = 0.20
DODGE_SPD_MS      = 0.40; HISTORY_LEN       = 20
CAM_W, CAM_H      = 640,  480
FOCAL_EST         = CAM_W * 0.8
CX, CY            = CAM_W / 2, CAM_H / 2
MAX_CAMS          = 8
DEFAULT_BASELINE  = 1.50

# OpenCV BGR
BLK=(8,8,12);   WHT=(255,255,255); GRY=(120,120,120)
RED=(30,30,220); BLU=(255,180,20);  CYN=(230,230,20)
GRN=(60,230,60); ORG=(0,165,255);   MAG=(220,30,220); YLW=(0,210,230)
FD=cv2.FONT_HERSHEY_DUPLEX; FS=cv2.FONT_HERSHEY_SIMPLEX

# HSV ranges
R_LO1=np.array([0,120,70],np.uint8);   R_HI1=np.array([10,255,255],np.uint8)
R_LO2=np.array([165,120,70],np.uint8); R_HI2=np.array([180,255,255],np.uint8)
B_LO =np.array([90,100,50],np.uint8);  B_HI =np.array([140,255,255],np.uint8)
W_S_MAX=55; W_V_MIN=160
SK1_LO=np.array([0,20,60],np.uint8);   SK1_HI=np.array([25,210,255],np.uint8)
SK2_LO=np.array([0,10,40],np.uint8);   SK2_HI=np.array([20,130,210],np.uint8)

# GUI hex – SOLO para CTk widgets (nunca tuplas BGR)
GUI_BG      = "#0d0d12"; GUI_PANEL   = "#13131a"; GUI_CARD    = "#1a1a24"
GUI_BORDER  = "#2a2a3a"; GUI_RED     = "#e03030"; GUI_BLUE    = "#2080ff"
GUI_CYAN    = "#00e5e5"; GUI_GREEN   = "#30e060"; GUI_YELLOW  = "#e0c020"
GUI_MAGENTA = "#cc30cc"; GUI_WHITE   = "#e8e8f0"; GUI_GRAY    = "#505060"
GUI_ORANGE  = "#ff8c00"; GUI_BLACK   = "#08080c"

# ══════════════════════════════════════════════════════════════════
#  CAMERA DETECTION  — selección por FPS máximo por dispositivo
# ══════════════════════════════════════════════════════════════════
def _get_dshow_names():
    try:
        ps = ("Get-PnpDevice -Class Camera -Status OK "
              "| Sort-Object InstanceId "
              "| Select-Object -ExpandProperty FriendlyName "
              "| ConvertTo-Json")
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            timeout=6, stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore").strip()
        if not out: return []
        import json as _j; data = _j.loads(out)
        return [data] if isinstance(data, str) else list(data)
    except:
        return []

def detect_cameras():
    """
    Escanea índices 0..MAX_CAMS con DSHOW.
    Cada índice OpenCV que entregue frames válidos es tratado como
    dispositivo independiente — incluso si comparten nombre (ej: 2× Camo).
    Cuando el mismo nombre aparece más de una vez se añade un sufijo
    (#1, #2…) para distinguirlos en la UI.
    Devuelve los primeros 3 encontrados ordenados por índice.
    """
    dev_names = _get_dshow_names()
    print(f"\nDetectando cámaras...")
    if dev_names:
        print(f"  Dispositivos Windows ({len(dev_names)}): {', '.join(dev_names)}")

    raw = []
    name_count = {}   # para desambiguar nombres duplicados

    for i in range(MAX_CAMS):
        try:
            # Intentar MSMF primero — soporta múltiples cámaras del mismo modelo
            cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release(); time.sleep(0.15); continue
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.release(); time.sleep(0.15); continue

            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            # Medir FPS empíricamente si el driver no reporta valor válido
            if fps <= 0 or fps > 240:
                t0 = time.time()
                for _ in range(10): cap.read()
                fps = round(10 / max(time.time() - t0, 0.001), 1)
            cap.release()
            time.sleep(0.15)  # dejar que el driver limpie antes del próximo probe

            base_name = dev_names[i] if i < len(dev_names) else f"Camara {i}"

            # Desambiguar si el mismo nombre ya apareció antes
            name_count[base_name] = name_count.get(base_name, 0) + 1
            if name_count[base_name] > 1:
                display_name = f"{base_name} #{name_count[base_name]}"
            else:
                display_name = base_name

            label = f"{display_name}  [{w}x{h} @ {fps:.0f}fps]"
            raw.append({'index': i, 'w': w, 'h': h, 'fps': fps,
                        'name': display_name, 'label': label})
            print(f"  [OK]  idx={i}  {label}")
        except:
            time.sleep(0.15)

    # Sin agrupamiento — cada índice OpenCV = 1 cámara
    # Ordenar por FPS descendente para poner las más fluidas primero
    raw.sort(key=lambda c: (c['fps'], c['w'] * c['h']), reverse=True)
    result = raw[:3]

    print(f"\n  Seleccionadas: {len(result)}/3")
    for c in result:
        print(f"    → idx={c['index']}  {c['label']}")
    print()
    return result

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
        if Z < 0.1 or Z > 20.0: return None
        X = Z * (float(u_a) - self.cx) / self.f
        Y = Z * (float(v_a) - self.cy) / self.f
        return (X, Y, Z)

    def depth_from_single(self, u, v, z=2.0):
        return (z * (float(u) - self.cx) / self.f, z * (float(v) - self.cy) / self.f, z)

    def fuse_keypoints(self, kp_a, kp_b, cf_a=None, cf_b=None):
        n = 17; fused = np.zeros((n, 2), np.float32); pts3d = {}; origin = {}
        for i in range(n):
            av = (i < len(kp_a) and not (kp_a[i][0] == 0 and kp_a[i][1] == 0)
                  and 0 < kp_a[i][0] < CAM_W and 0 < kp_a[i][1] < CAM_H)
            bv = (i < len(kp_b) and not (kp_b[i][0] == 0 and kp_b[i][1] == 0)
                  and 0 < kp_b[i][0] < CAM_W and 0 < kp_b[i][1] < CAM_H)
            ca = float(cf_a[i]) if (cf_a is not None and i < len(cf_a)) else 0.5
            cb = float(cf_b[i]) if (cf_b is not None and i < len(cf_b)) else 0.5
            if av and bv:
                p3 = self.triangulate(kp_a[i][0], kp_a[i][1], kp_b[i][0], kp_b[i][1])
                if p3:
                    pts3d[i] = p3; origin[i] = 'AB'; fused[i] = kp_a[i][:2]
                else:
                    fused[i] = kp_a[i][:2] if ca >= cb else kp_b[i][:2]
                    pts3d[i] = self.depth_from_single(*fused[i])
                    origin[i] = 'A' if ca >= cb else 'B'
            elif av:
                fused[i] = kp_a[i][:2]; pts3d[i] = self.depth_from_single(*fused[i]); origin[i] = 'A'
            elif bv:
                fused[i] = kp_b[i][:2]; pts3d[i] = self.depth_from_single(*fused[i]); origin[i] = 'B'
        return fused, pts3d, origin

# ══════════════════════════════════════════════════════════════════
#  INFER THREAD
# ══════════════════════════════════════════════════════════════════
class InferThread(threading.Thread):
    def __init__(self, model, name="Infer"):
        super().__init__(daemon=True, name=name)
        self.model = model; self._fin = None; self._rout = None
        self._lk = threading.Lock(); self._ev = threading.Event(); self._go = True

    def submit(self, frame):
        with self._lk: self._fin = frame
        self._ev.set()

    def result(self):
        with self._lk: return self._rout

    def stop(self): self._go = False; self._ev.set()

    def run(self):
        while self._go:
            self._ev.wait(); self._ev.clear()
            if not self._go: break
            with self._lk: f = self._fin
            if f is None: continue
            try:
                r = self.model(f, imgsz=INFER_IMGSZ, conf=INFER_CONF, verbose=False)
                with self._lk: self._rout = r
            except Exception as e:
                print(f"[{self.name}] {e}")

# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def glow(img, c, r, col, n=3):
    for i in range(n, 0, -1): cv2.circle(img, c, r + i * 3, col, 1)
    cv2.circle(img, c, r, col, 2)

def classify_glove(frame, x, y, r=38):
    h, w = frame.shape[:2]
    roi = frame[max(0, y-r):min(h, y+r), max(0, x-r):min(w, x+r)]
    if roi.size == 0: return {'white': False, 'red': False, 'blue': False}
    small = cv2.resize(roi, (48, 48), interpolation=cv2.INTER_LINEAR)
    hsv = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]; mn = max(18, int(48 * 48 * 0.07))
    wm = (s < W_S_MAX) & (v > W_V_MIN); white = int(np.sum(wm)) > mn
    rm = cv2.bitwise_or(cv2.inRange(hsv, R_LO1, R_HI1), cv2.inRange(hsv, R_LO2, R_HI2))
    rm[wm] = 0; red = int(np.sum(rm > 0)) > mn
    bm = cv2.inRange(hsv, B_LO, B_HI); bm[wm] = 0; blue = int(np.sum(bm > 0)) > mn
    return {'white': white, 'red': red, 'blue': blue}

def bare_torso(frame, kp):
    if len(kp) < 13: return False
    try:
        pts = [kp[i] for i in [5, 6, 11, 12] if kp[i][0] > 0 and kp[i][1] > 0]
        if len(pts) < 3: return False
        xs = [int(p[0]) for p in pts]; ys = [int(p[1]) for p in pts]
        H, W = frame.shape[:2]
        roi = frame[max(0, min(ys)):min(H, max(ys)+20), max(0, min(xs)-10):min(W, max(xs)+10)]
        if roi.size == 0 or roi.shape[0] < 12 or roi.shape[1] < 12: return False
        sm = cv2.resize(roi, (64, 64), interpolation=cv2.INTER_LINEAR)
        hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
        sk = cv2.bitwise_or(cv2.inRange(hsv, SK1_LO, SK1_HI), cv2.inRange(hsv, SK2_LO, SK2_HI))
        return float(np.sum(sk > 0)) / (64 * 64) > 0.15
    except:
        return False

def torso_center_3d(pts3d):
    coords = [pts3d[i] for i in [5, 6, 11, 12] if i in pts3d]
    if len(coords) < 2: return None
    return tuple(np.mean(coords, axis=0))

def dist3d(a, b):
    if a is None or b is None: return 0.0
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))

# ══════════════════════════════════════════════════════════════════
#  HEAD TRACKER
# ══════════════════════════════════════════════════════════════════
class HeadTracker:
    def __init__(self):
        self.hist = deque(maxlen=24); self.prev_pos3d = self.prev_t = None
        self.total_d = self.max_spd = 0.0; self.dodges = 0; self._dodging = False
        self.cur_spd = 0.0; self.last_pos3d = self.last_pos2d = None

    def reset(self):
        self.hist.clear(); self.prev_pos3d = self.prev_t = None
        self.total_d = self.max_spd = 0.0; self.dodges = 0; self._dodging = False
        self.cur_spd = 0.0; self.last_pos3d = self.last_pos2d = None

    def update(self, pos3d, pos2d, t):
        self.last_pos3d = pos3d; self.last_pos2d = pos2d; spd = 0.0
        if self.prev_pos3d is not None:
            dt = t - self.prev_t
            if dt > 0.001:
                d = dist3d(pos3d, self.prev_pos3d); spd = d / dt; self.total_d += d
                if spd > self.max_spd: self.max_spd = spd
                if spd > DODGE_SPD_MS:
                    if not self._dodging: self.dodges += 1; self._dodging = True
                else:
                    self._dodging = False
        self.hist.append({'pos3d': pos3d, 'time': t})
        self.prev_pos3d = pos3d; self.prev_t = t; self.cur_spd = spd

    def agility(self):
        return round(min(self.total_d * 8, 40) + min(self.max_spd * 8, 35) + min(self.dodges * 2.5, 25), 1)

# ══════════════════════════════════════════════════════════════════
#  FIGHTER
# ══════════════════════════════════════════════════════════════════
class Fighter:
    def __init__(self, name, col):
        self.name = name; self.col = col
        self.strikes = self.connected = self.aggr = self.face_hits = 0
        self.max_spd_ms = self.max_ext_m = 0.0
        self.hL = deque(maxlen=HISTORY_LEN); self.hR = deque(maxlen=HISTORY_LEN)
        self.pL = self.pR = self.pt = None
        self.punchL = self.punchR = False; self.tL = self.tR = self.mL = self.mR = 0.0
        self.ptypes = {"JAB": 0, "CROSS": 0, "HOOK": 0, "UPPERCUT": 0, "OVERHAND": 0}
        self.head = HeadTracker(); self._lfht = 0.0
        self.spd_history = deque(maxlen=60)

    def reset(self):
        self.strikes = self.connected = self.aggr = self.face_hits = 0
        self.max_spd_ms = self.max_ext_m = 0.0
        self.hL.clear(); self.hR.clear()
        self.pL = self.pR = self.pt = None
        self.punchL = self.punchR = False; self.tL = self.tR = self.mL = self.mR = 0.0
        self.ptypes = {"JAB": 0, "CROSS": 0, "HOOK": 0, "UPPERCUT": 0, "OVERHAND": 0}
        self.head.reset(); self._lfht = 0.0; self.spd_history.clear()

    def accuracy(self):
        return round(self.connected / max(1, self.strikes) * 100, 1)

    def _classify(self, wp3, sp3, left, vel3, dur, mx):
        if sp3 is None: return "UNKNOWN"
        vx, vy, vz = vel3; spd = math.sqrt(vx*vx + vy*vy + vz*vz)
        if spd < 0.01: return "UNKNOWN"
        vyn = vy / spd; lat = abs(vx) / (abs(vz) + 0.001)
        hdiff = sp3[1] - wp3[1]
        if vyn < -0.4 and hdiff < 0.1: return "UPPERCUT"
        if lat > 0.8:
            return ("OVERHAND" if vyn > 0.2 and mx > EXTENSION_THR_M * 1.8 and dur > 0.18 else "HOOK")
        if left:
            if lat < 1.5 and dur < 0.25 and mx > EXTENSION_THR_M * 1.5: return "JAB"
        else:
            if lat < 1.5 and mx > EXTENSION_THR_M * 1.6: return "CROSS"
        return "JAB" if left else "CROSS"

    def update_punch(self, wp3, left, sp3, t):
        hist = self.hL if left else self.hR
        prev3 = self.pL if left else self.pR
        active = self.punchL if left else self.punchR
        ext = dist3d(wp3, sp3) if sp3 else 0.0
        vel3 = (0.0, 0.0, 0.0); spd = 0.0
        hist.append({'pos3d': wp3, 'time': t, 'ext': ext})
        if prev3 and self.pt:
            dt = t - self.pt
            if dt > 0.001:
                dvx = wp3[0]-prev3[0]; dvy = wp3[1]-prev3[1]; dvz = wp3[2]-prev3[2]
                spd = math.sqrt(dvx*dvx + dvy*dvy + dvz*dvz) / dt
                vel3 = (dvx/dt, dvy/dt, dvz/dt)
        hl = len(hist)
        if hl >= 3:
            rec = list(hist); sw = []
            for a, b in ((rec[-3], rec[-2]), (rec[-2], rec[-1])):
                dtw = b['time'] - a['time']
                if dtw > 0.001: sw.append(dist3d(b['pos3d'], a['pos3d']) / dtw)
            if sw: spd = float(np.mean(sw))
        spd = min(spd, PUNCH_SPD_CAP_MS)
        if spd > self.max_spd_ms: self.max_spd_ms = spd
        if ext > self.max_ext_m: self.max_ext_m = ext
        self.spd_history.append(spd)
        new_p = False; ptype = "UNKNOWN"
        if hl >= 3:
            if spd > PUNCH_SPD_THR_MS and ext > EXTENSION_THR_M and not active:
                if left: self.punchL = True; self.tL = t; self.mL = ext
                else:    self.punchR = True; self.tR = t; self.mR = ext
            elif active:
                if left:
                    if ext > self.mL: self.mL = ext
                    cur = self.mL; dur = t - self.tL
                else:
                    if ext > self.mR: self.mR = ext
                    cur = self.mR; dur = t - self.tR
                retracted = ext < cur * RETRACTION_RATIO; slow = spd < PUNCH_SPD_THR_MS * 0.7
                dur_ok = MIN_PUNCH_DUR < dur < MAX_PUNCH_DUR; peak_ok = cur > EXTENSION_THR_M * 1.3
                if retracted and slow and dur_ok and peak_ok:
                    av3 = vel3
                    if hl >= 4:
                        seg = list(hist)[-4:]; vxs = []; vys = []; vzs = []
                        for i in range(len(seg) - 1):
                            dt2 = seg[i+1]['time'] - seg[i]['time']
                            if dt2 > 0.001:
                                vxs.append((seg[i+1]['pos3d'][0] - seg[i]['pos3d'][0]) / dt2)
                                vys.append((seg[i+1]['pos3d'][1] - seg[i]['pos3d'][1]) / dt2)
                                vzs.append((seg[i+1]['pos3d'][2] - seg[i]['pos3d'][2]) / dt2)
                        if vxs: av3 = (float(np.mean(vxs)), float(np.mean(vys)), float(np.mean(vzs)))
                    new_p = True; self.strikes += 1; self.aggr += 1
                    ptype = self._classify(wp3, sp3, left, av3, dur, cur)
                    if ptype in self.ptypes: self.ptypes[ptype] += 1
                    if left: self.punchL = False; self.mL = 0.0
                    else:    self.punchR = False; self.mR = 0.0
                elif dur >= MAX_PUNCH_DUR:
                    if left: self.punchL = False; self.mL = 0.0
                    else:    self.punchR = False; self.mR = 0.0
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
            wc = sum(d['W']); rc = sum(d['R']); bc = sum(d['B'])
            if wc >= VOTE_NEEDED and wc >= rc and wc >= bc:
                if self.mode == "none":
                    self.test_pid = pid; self.mode = "test"; self.locked = True; return True
            if rc >= VOTE_NEEDED and self.red_pid is None and self.mode != "test":
                self.red_pid = pid; self.mode = "fight"
            if bc >= VOTE_NEEDED and self.blue_pid is None and self.mode != "test":
                self.blue_pid = pid; self.mode = "fight"
        if self.red_pid and self.blue_pid: self.locked = True
        return False

    def clear(self):
        self._wins.clear(); self.locked = False
        self.test_pid = self.red_pid = self.blue_pid = None; self.mode = "none"

    def force_test(self, pid): self.clear(); self.test_pid = pid; self.mode = "test"; self.locked = True
    def force_red(self, pid):
        self.red_pid = pid; self.mode = "fight"
        if self.blue_pid: self.locked = True
    def force_blue(self, pid):
        self.blue_pid = pid; self.mode = "fight"
        if self.red_pid: self.locked = True

    @property
    def ready(self):
        return (self.mode == "test" or
                (self.mode == "fight" and self.red_pid is not None and self.blue_pid is not None))

# ══════════════════════════════════════════════════════════════════
#  VISION ENGINE  — 3 cámaras
# ══════════════════════════════════════════════════════════════════
class VisionEngine(threading.Thread):
    def __init__(self, cam_a_idx, cam_b_idx, cam_c_idx, baseline_m):
        super().__init__(daemon=True)
        self.cam_a_idx = cam_a_idx
        self.cam_b_idx = cam_b_idx
        self.cam_c_idx = cam_c_idx
        self.stereo_ab = StereoFuser(baseline_m=baseline_m)
        self.stereo_ac = StereoFuser(baseline_m=baseline_m * 1.2)

        self.roles = RoleDetector()
        self.red  = Fighter("ROJA", RED)
        self.blue = Fighter("AZUL", BLU)

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

    def _fresh_ts(self):
        return {'fp': 0, 'dv': 0, 'pd': 0, 'hd': 0,
                'ss': deque(maxlen=500), 'es': deque(maxlen=500),
                'cc': {"JAB": 0, "CROSS": 0, "HOOK": 0, "UPPERCUT": 0, "OVERHAND": 0, "UNKNOWN": 0}}

    def _reset_ts(self): self._ts = self._fresh_ts(); self._ts_t0 = time.time()

    @property
    def tm(self): return self.roles.mode == "test"

    def _score(self, f):
        if f.strikes == 0: return 0.0
        return f.connected / max(1, f.strikes) * 100 + f.aggr * 0.2 + f.max_spd_ms * 2

    def _check_hit(self, wp3, pid):
        hb = hf = False
        rp = self.roles.red_pid; bp = self.roles.blue_pid
        opp = bp if pid == rp else (rp if pid == bp else None)
        if opp and opp in self.opp_pos3d:
            hb = dist3d(wp3, self.opp_pos3d[opp]) < HIT_R_M
        oh = (self.blue.head.last_pos3d if pid == rp else self.red.head.last_pos3d)
        if oh: hf = dist3d(wp3, oh) < HEAD_HIT_R_M
        return hb, hf

    @staticmethod
    def _parse_result(res):
        out = []
        if res is None: return out
        try:
            kps_xy   = res[0].keypoints.xy.cpu().numpy()
            kps_conf = res[0].keypoints.conf
            kps_conf = (kps_conf.cpu().numpy() if kps_conf is not None
                        else np.ones((len(kps_xy), 17), np.float32) * 0.5)
            for kp, cf in zip(kps_xy, kps_conf):
                if kp is None or len(kp) < 11: continue
                out.append((kp, cf))
        except:
            pass
        return out

    def _process_cam(self, frame, res, pid_offset=0):
        persons = []; fh, fw = frame.shape[:2]
        for idx, (kp, cf) in enumerate(self._parse_result(res)):
            lw = kp[9]; rw = kp[10]
            lx, ly = float(lw[0]), float(lw[1]); rx, ry = float(rw[0]), float(rw[1])
            lv = not (lx == 0 and ly == 0) and 0 <= lx < fw and 0 <= ly < fh
            rv = not (rx == 0 and ry == 0) and 0 <= rx < fw and 0 <= ry < fh
            if not lv and not rv: continue
            cL = classify_glove(frame, int(lx), int(ly)) if lv else {}
            cR = classify_glove(frame, int(rx), int(ry))  if rv else {}
            gi = {'white': cL.get('white', False) or cR.get('white', False),
                  'red':   cL.get('red',   False) or cR.get('red',   False),
                  'blue':  cL.get('blue',  False) or cR.get('blue',  False),
                  'bare':  bare_torso(frame, kp)}
            persons.append((idx + pid_offset, kp, cf, gi))
        return persons

    def _find_match(self, kp_a, persons_sec):
        best = None; best_d = 9999
        for _, kp_b, cf_b, _ in persons_sec:
            na = kp_a[0]; nb = kp_b[0]
            if na[0] > 0 and nb[0] > 0:
                d = math.hypot(na[0] - nb[0], na[1] - nb[1])
                if d < best_d: best_d = d; best = (kp_b, cf_b)
        return best

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock: self._log_msgs.append(f"[{ts}] {msg}")

    def _end_round(self):
        sc = self._score(self.red)
        if self.tm:
            acc = self.red.connected / max(1, self.red.strikes) * 100
            self.rnd_stats[self.rnd] = {
                "mode": "test", "strikes": self.red.strikes,
                "connected": self.red.connected,
                "max_speed_ms": self.red.max_spd_ms,
                "max_ext_m": self.red.max_ext_m,
                "score": sc, "punch_types": self.red.ptypes.copy(),
                "accuracy": round(acc, 1)}
            self.rnd_winners[self.rnd] = "test"; self._reset_ts()
            self._log(f"Round {self.rnd}: TEST — {self.red.strikes} golpes, {acc:.1f}%")
        else:
            rs = self._score(self.red); bs = self._score(self.blue)
            w = "draw" if rs == bs else ("red" if rs > bs else "blue")
            self.rnd_winners[self.rnd] = w
            self.rnd_stats[self.rnd] = {
                "winner": w, "red_score": rs, "blue_score": bs,
                "red":  {"strikes": self.red.strikes,  "connected": self.red.connected,
                         "face_hits": self.red.face_hits,  "max_speed_ms": self.red.max_spd_ms,
                         "dodges": self.red.head.dodges,   "punch_types": self.red.ptypes.copy()},
                "blue": {"strikes": self.blue.strikes, "connected": self.blue.connected,
                         "face_hits": self.blue.face_hits, "max_speed_ms": self.blue.max_spd_ms,
                         "dodges": self.blue.head.dodges,  "punch_types": self.blue.ptypes.copy()}}
            self._log(f"Round {self.rnd}: ganador {w.upper()}")

    # ── Controles ──────────────────────────────────────────────────
    def cmd_start(self):
        if not self.roles.ready: return False
        self.session_state = "RUNNING"; self.phase = "ROUND"
        self.rnd = 1; self.rnd_done = 0
        self.t_start = time.time(); self.t_paused = 0.0; self.t_pause = 0.0
        self.red.reset(); self.blue.reset()
        self.rnd_stats = {}; self.rnd_winners = {}; self._reset_ts()
        self._log("=== SESIÓN INICIADA ==="); return True

    def cmd_pause(self):
        if self.session_state == "RUNNING":
            self.session_state = "PAUSED"; self.t_pause = time.time(); self._log("Pausa")
        elif self.session_state == "PAUSED":
            self.t_paused += time.time() - self.t_pause
            self.session_state = "RUNNING"; self._log("Resume")

    def cmd_end_round(self):
        if self.session_state in ("RUNNING", "PAUSED") and self.phase == "ROUND":
            self._end_round(); self.rnd_done += 1

    def cmd_force_test(self, pid=None):
        p = pid if pid is not None else (self._pids[0] if self._pids else 0)
        self.roles.force_test(p); self._log(f"Rol TEST → pid {p}")

    def cmd_force_red(self, pid=None):
        p = pid if pid is not None else (self._pids[0] if self._pids else 0)
        if not self.roles.locked: self.roles.force_red(p); self._log(f"Rol ROJO → pid {p}")

    def cmd_force_blue(self, pid=None):
        p = pid if pid is not None else (self._pids[1] if len(self._pids) > 1 else (self._pids[0] if self._pids else 1))
        if not self.roles.locked: self.roles.force_blue(p); self._log(f"Rol AZUL → pid {p}")

    def cmd_clear(self): self.roles.clear(); self._log("Roles limpiados")
    def cmd_stop(self):  self._go = False

    def get_frames(self):
        with self._lock: return self._frame_a, self._frame_b, self._frame_c

    def get_stats(self):
        with self._lock: return dict(self._stats)

    def get_logs(self):
        with self._lock: return list(self._log_msgs)

    # ── Loop principal ─────────────────────────────────────────────
    def run(self):
        def open_cap(idx):
            c = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            c.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
            c.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
            c.set(cv2.CAP_PROP_FPS, 30)
            c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return c

        self._log("Cargando modelo YOLO...")
        model  = YOLO("yolov8n-pose.pt")
        inf_a  = InferThread(model, "InferA"); inf_a.start()
        inf_b  = InferThread(model, "InferB") if self.cam_b_idx is not None else None
        inf_c  = InferThread(model, "InferC") if self.cam_c_idx is not None else None
        if inf_b: inf_b.start()
        if inf_c: inf_c.start()

        cap_a = open_cap(self.cam_a_idx)
        cap_b = open_cap(self.cam_b_idx) if self.cam_b_idx is not None else None
        cap_c = open_cap(self.cam_c_idx) if self.cam_c_idx is not None else None

        last_a = last_b = last_c = None; fc = 0
        self._log("Sistema listo ✓")

        while self._go:
            ret_a, frame_a = cap_a.read()
            if not ret_a: time.sleep(0.01); continue
            frame_a = cv2.flip(frame_a, 1)

            frame_b = frame_c = None
            if cap_b:
                ret_b, frame_b = cap_b.read()
                if ret_b: frame_b = cv2.flip(frame_b, 1)
            if cap_c:
                ret_c, frame_c = cap_c.read()
                if ret_c: frame_c = cv2.flip(frame_c, 1)

            fc += 1; ct = time.time()

            if fc % INFER_EVERY == 0:
                inf_a.submit(frame_a)
                if inf_b and frame_b is not None: inf_b.submit(frame_b)
                if inf_c and frame_c is not None: inf_c.submit(frame_c)

            r_a = inf_a.result()
            r_b = inf_b.result() if inf_b else None
            r_c = inf_c.result() if inf_c else None
            if r_a is not None: last_a = r_a
            if r_b is not None: last_b = r_b
            if r_c is not None: last_c = r_c

            def safe_plot(last, frame):
                try:
                    return (last[0].plot() if last and frame is not None
                            else (frame.copy() if frame is not None
                                  else np.zeros((CAM_H, CAM_W, 3), np.uint8)))
                except:
                    return frame.copy() if frame is not None else np.zeros((CAM_H, CAM_W, 3), np.uint8)

            img_a = cv2.resize(safe_plot(last_a, frame_a), (CAM_W, CAM_H))
            img_b = cv2.resize(safe_plot(last_b, frame_b), (CAM_W, CAM_H))
            img_c = cv2.resize(safe_plot(last_c, frame_c), (CAM_W, CAM_H))

            if self.tm and self.session_state == "RUNNING": self._ts['fp'] += 1

            persons_a = self._process_cam(frame_a, last_a, 0)
            persons_b = self._process_cam(frame_b if frame_b is not None else frame_a, last_b, 100)
            persons_c = self._process_cam(frame_c if frame_c is not None else frame_a, last_c, 200)

            fused_data = {}; n_3d = n_total = 0

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                match_b = self._find_match(kp_a, persons_b)
                match_c = self._find_match(kp_a, persons_c)
                if match_b:
                    fused_kp, pts3d, origin = self.stereo_ab.fuse_keypoints(kp_a, match_b[0], cf_a, match_b[1])
                    n_3d += sum(1 for o in origin.values() if o == 'AB')
                    if match_c:
                        _, pts3d_c, orig_c = self.stereo_ac.fuse_keypoints(kp_a, match_c[0], cf_a, match_c[1])
                        for ki in pts3d:
                            if ki in pts3d_c and orig_c.get(ki) == 'AB':
                                pts3d[ki] = tuple((np.array(pts3d[ki]) + np.array(pts3d_c[ki])) / 2)
                                origin[ki] = 'ABC'
                elif match_c:
                    fused_kp, pts3d, origin = self.stereo_ac.fuse_keypoints(kp_a, match_c[0], cf_a, match_c[1])
                    n_3d += sum(1 for o in origin.values() if o == 'AB')
                else:
                    pts3d = {i: self.stereo_ab.depth_from_single(kp_a[i][0], kp_a[i][1])
                             for i in range(min(17, len(kp_a)))
                             if not (kp_a[i][0] == 0 and kp_a[i][1] == 0)}
                    fused_kp = kp_a; origin = {i: 'A' for i in pts3d}
                fused_data[pid_a] = {'fused_kp': fused_kp, 'pts3d': pts3d, 'origin': origin}
                n_total += len(origin)

            new_pos3d = {}
            for pid, fd in fused_data.items():
                tc3 = torso_center_3d(fd['pts3d'])
                if tc3: new_pos3d[pid] = tc3
            if new_pos3d: self.opp_pos3d = new_pos3d

            self._pids = [pid for pid, _, _, _ in persons_a]

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                bare = gi_a.get('bare', False)
                self.roles.update(pid_a,
                    w_ok=gi_a.get('white', False) and bare,
                    r_ok=gi_a.get('red',   False) and bare,
                    b_ok=gi_a.get('blue',  False) and bare)
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

            can_det = self.session_state == "RUNNING" and self.phase == "ROUND"
            rp = self.roles.red_pid; bp = self.roles.blue_pid; tp = self.roles.test_pid
            GLOVE_R = 36; HEAD_R = 30

            for pid_a, kp_a, cf_a, gi_a in persons_a:
                fd     = fused_data.get(pid_a, {})
                pts3d  = fd.get('pts3d', {})
                origin = fd.get('origin', {})
                fused_kp = fd.get('fused_kp', kp_a)
                ftr = None; rcol = GRY; rlbl = "?"
                if pid_a == rp:   ftr = self.red;  rcol = RED; rlbl = "RED"
                elif pid_a == bp: ftr = self.blue; rcol = BLU; rlbl = "BLU"
                elif pid_a == tp: ftr = self.red;  rcol = WHT; rlbl = "TEST"

                nose_p3  = pts3d.get(0)
                nose_2d  = fused_kp[0] if len(fused_kp) > 0 and fused_kp[0][0] > 0 else None
                if ftr and nose_p3 and nose_2d is not None:
                    ftr.head.update(nose_p3, (int(nose_2d[0]), int(nose_2d[1])), ct)
                    for i in range(3, 0, -1):
                        cv2.circle(img_a, (int(nose_2d[0]), int(nose_2d[1])), HEAD_R + i*3, rcol, 1)
                    cv2.circle(img_a, (int(nose_2d[0]), int(nose_2d[1])), HEAD_R, rcol, 2)
                    if ftr.face_hits > 0 and ct - ftr._lfht < 0.4:
                        cv2.putText(img_a, "FACE!", (int(nose_2d[0])-20, int(nose_2d[1])+HEAD_R+18),
                                    FD, 0.60, GRN, 2)

                for wi, il in ((9, True), (10, False)):
                    if wi >= len(kp_a): continue
                    wx2d = kp_a[wi]; wx, wy = int(float(wx2d[0])), int(float(wx2d[1]))
                    if wx == 0 and wy == 0: continue
                    if not (0 <= wx < CAM_W and 0 <= wy < CAM_H): continue
                    glow(img_a, (wx, wy), GLOVE_R+6, rcol, n=2)
                    cv2.circle(img_a, (wx, wy), GLOVE_R, rcol, 2)
                    lx, ly = wx-28, wy-GLOVE_R-26
                    cv2.rectangle(img_a, (lx-4, ly-18), (lx+72, ly+4), BLK, -1)
                    cv2.putText(img_a, rlbl, (lx, ly), FD, 0.54, rcol, 2)
                    org_tag = origin.get(wi, '?')
                    org_c = GRN if org_tag in ('AB', 'ABC') else (YLW if org_tag == 'A' else ORG)
                    cv2.putText(img_a, org_tag, (wx+GLOVE_R+2, wy+4), FS, 0.30, org_c, 1)

                    if pid_a == tp and self.tm:
                        pulse = int(7 * math.sin(ct * 9)) + 7
                        glow(img_a, (wx, wy), GLOVE_R+12+pulse, RED, n=2)

                    if ftr and can_det:
                        wp3 = pts3d.get(wi); sp3 = pts3d.get(5 if il else 6)
                        if wp3 is None: continue
                        try:
                            np2, spd, ptype, active = ftr.update_punch(wp3, il, sp3, ct)
                            if self.tm: self._ts['dv'] += 1
                            if active: cv2.circle(img_a, (wx, wy), GLOVE_R-8, ORG, -1)
                            if sp3:
                                ext_m = dist3d(wp3, sp3)
                                cv2.putText(img_a, f"{ext_m:.2f}m", (wx+GLOVE_R+2, wy-6),
                                            FS, 0.34, GRN if ext_m > EXTENSION_THR_M else YLW, 1)
                            if spd > 0.1:
                                cv2.putText(img_a, f"{spd:.1f}m/s", (wx-GLOVE_R-52, wy), FS, 0.34, CYN, 1)
                            if self.tm:
                                if spd > 0 and math.isfinite(spd): self._ts['ss'].append(spd)
                                if sp3:
                                    e2 = dist3d(wp3, sp3)
                                    if math.isfinite(e2): self._ts['es'].append(e2)
                            if np2:
                                if self.tm:
                                    self._ts['pd'] += 1
                                    if ptype in self._ts['cc']: self._ts['cc'][ptype] += 1
                                if self.tm:
                                    hn  = ftr.hL if il else ftr.hR
                                    pk  = max((h.get('ext', 0) for h in hn), default=0)
                                    hb  = pk > EXTENSION_THR_M * 2.5; hf = False
                                else:
                                    hb, hf = self._check_hit(wp3, pid_a)
                                if hb or hf:
                                    ftr.connected += 1
                                    if self.tm: self._ts['hd'] += 1
                                    if hf:
                                        ftr.face_hits += 1; ftr._lfht = ct
                                        cv2.putText(img_a, "FACE HIT!", (wx-36, wy+GLOVE_R+24), FD, 0.66, GRN, 2)
                                    else:
                                        cv2.putText(img_a, "HIT!", (wx-20, wy+GLOVE_R+24), FD, 0.66, GRN, 2)
                                    glow(img_a, (wx, wy), GLOVE_R+12, GRN, n=3)
                                else:
                                    glow(img_a, (wx, wy), GLOVE_R+9, CYN, n=2)
                                cv2.putText(img_a, ptype, (wx-28, wy-GLOVE_R-22), FD, 0.50, YLW, 2)
                        except:
                            pass

            # Timer
            rem = 0
            if self.session_state == "RUNNING":
                el = time.time() - self.t_start - self.t_paused
                if self.phase == "ROUND":
                    rem = max(0, int(ROUND_TIME - el))
                    if rem == 0:
                        self._end_round(); self.rnd_done += 1
                        if self.rnd_done >= TOTAL_ROUNDS:
                            self._log("=== SESIÓN TERMINADA ===")
                            self.session_state = "IDLE"; self.phase = "IDLE"
                        else:
                            self.phase = "REST"; self.t_start = time.time()
                else:
                    rem = max(0, int(REST_TIME - el))
                    if rem == 0:
                        self.rnd += 1; self.phase = "ROUND"
                        self.t_start = time.time(); self.t_paused = 0.0
                        self.red.reset(); self.blue.reset()
                        if self.tm: self._reset_ts()
            elif self.session_state == "PAUSED":
                el  = self.t_pause - self.t_start - self.t_paused
                lim = ROUND_TIME if self.phase == "ROUND" else REST_TIME
                rem = max(0, int(lim - el))

            m2, s2 = rem // 60, rem % 60
            st, ph = self.session_state, self.phase
            ptxt, pc = (("IDLE",  GRY) if st == "IDLE" else
                        ("PAUSA", RED) if st == "PAUSED" else
                        ("LIVE",  GRN) if ph == "ROUND" else ("REST", YLW))
            mtxt, mc = (("TEST",   MAG) if self.tm else
                        ("FIGHT",  CYN) if self.roles.mode == "fight" else ("DETECT", GRY))

            def hud(img, label, lc):
                cv2.rectangle(img, (0, 0), (CAM_W, 58), BLK, -1)
                cv2.line(img, (0, 57), (CAM_W, 57), lc, 2)
                tstxt = f"{m2:02d}:{s2:02d}"
                cv2.putText(img, tstxt, (CAM_W//2-52, 44), FD, 1.20, (40, 40, 50), 4)
                cv2.putText(img, tstxt, (CAM_W//2-52, 44), FD, 1.20, WHT, 2)
                cv2.putText(img, label, (10, 38), FS, 0.42, lc, 1)
                cv2.putText(img, ptxt,  (CAM_W-72, 20), FS, 0.42, pc, 1)
                cv2.putText(img, mtxt,  (CAM_W-72, 54), FS, 0.42, mc, 1)

            hud(img_a, f"CAM A · PRINCIPAL · 3D:{n_3d}/{max(n_total,1)}", GRN)
            hud(img_b, "CAM B · ÁNGULO B", MAG)
            hud(img_c, "CAM C · ÁNGULO C", CYN)

            stats = {
                'rem': rem, 'rnd': self.rnd, 'phase': ph, 'state': st,
                'mode': self.roles.mode, 'mode_tm': self.tm,
                'status_msg': self._status_msg, 'roles_ready': self.roles.ready,
                'red': {
                    'strikes': self.red.strikes, 'connected': self.red.connected,
                    'face_hits': self.red.face_hits, 'accuracy': self.red.accuracy(),
                    'max_spd': round(self.red.max_spd_ms, 2), 'max_ext': round(self.red.max_ext_m, 2),
                    'agility': self.red.head.agility(), 'dodges': self.red.head.dodges,
                    'score': round(self._score(self.red), 1), 'ptypes': dict(self.red.ptypes),
                },
                'blue': {
                    'strikes': self.blue.strikes, 'connected': self.blue.connected,
                    'face_hits': self.blue.face_hits, 'accuracy': self.blue.accuracy(),
                    'max_spd': round(self.blue.max_spd_ms, 2), 'max_ext': round(self.blue.max_ext_m, 2),
                    'agility': self.blue.head.agility(), 'dodges': self.blue.head.dodges,
                    'score': round(self._score(self.blue), 1), 'ptypes': dict(self.blue.ptypes),
                },
                'rnd_winners': dict(self.rnd_winners),
                'n_3d': n_3d, 'n_kp': n_total, 'baseline': self.stereo_ab.B,
            }

            with self._lock:
                self._frame_a = img_a.copy()
                self._frame_b = img_b.copy()
                self._frame_c = img_c.copy()
                self._stats   = stats

        inf_a.stop()
        if inf_b: inf_b.stop()
        if inf_c: inf_c.stop()
        cap_a.release()
        if cap_b: cap_b.release()
        if cap_c: cap_c.release()

# ══════════════════════════════════════════════════════════════════
#  STAT CARD
# ══════════════════════════════════════════════════════════════════
class StatCard(ctk.CTkFrame):
    def __init__(self, parent, label, value="—", unit="", accent=GUI_CYAN, **kw):
        super().__init__(parent, fg_color=GUI_CARD, corner_radius=8, **kw)
        ctk.CTkLabel(self, text=label,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=GUI_GRAY).pack(anchor="w", padx=8, pady=(6, 0))
        self._val = ctk.CTkLabel(self, text=value,
            font=ctk.CTkFont("Courier New", 18, weight="bold"), text_color=accent)
        self._val.pack(anchor="w", padx=8)
        ctk.CTkLabel(self, text=unit if unit else " ",
            font=ctk.CTkFont(size=8), text_color=GUI_GRAY
        ).pack(anchor="w", padx=8, pady=(0, 6))

    def set(self, value): self._val.configure(text=str(value))

# ══════════════════════════════════════════════════════════════════
#  MAIN GUI
# ══════════════════════════════════════════════════════════════════
class FighterIDApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("FighterID Vision v3.2  —  3-Camera Stereo Biomechanics")
        self.configure(fg_color=GUI_BG)

        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{min(sw, 1440)}x{min(sh, 900)}+0+0")

        self._engine: VisionEngine = None
        self._cameras = []; self._running = False

        self._build_ui()
        # ── FIX TclError: diferir detección hasta que mainloop esté activo ──
        self.after(300, self._detect_and_start)

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ────────────────────────────────────────────────
        top = ctk.CTkFrame(self, height=52, fg_color=GUI_PANEL, corner_radius=0)
        top.pack(fill="x", side="top"); top.pack_propagate(False)

        ctk.CTkLabel(top, text="⬡  FIGHTER ID  v3.2",
            font=ctk.CTkFont("Courier New", 16, weight="bold"),
            text_color=GUI_CYAN).pack(side="left", padx=18, pady=12)

        self._top_status = ctk.CTkLabel(top, text="Iniciando...",
            font=ctk.CTkFont(size=11), text_color=GUI_GRAY)
        self._top_status.pack(side="left", padx=10)

        self._timer_lbl = ctk.CTkLabel(top, text="03:00",
            font=ctk.CTkFont("Courier New", 26, weight="bold"),
            text_color=GUI_WHITE)
        self._timer_lbl.pack(side="right", padx=24)

        self._round_lbl = ctk.CTkLabel(top, text="ROUND 1",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=GUI_WHITE)
        self._round_lbl.pack(side="right", padx=4)

        self._phase_lbl = ctk.CTkLabel(top, text="IDLE",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=GUI_GRAY)
        self._phase_lbl.pack(side="right", padx=10)

        # ── Layout principal ────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # Sidebar izquierdo
        sidebar = ctk.CTkFrame(main, width=162, fg_color=GUI_PANEL, corner_radius=0)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Zona central
        center = ctk.CTkFrame(main, fg_color=GUI_BG)
        center.pack(side="left", fill="both", expand=True)
        self._build_center(center)

    def _build_sidebar(self, parent):
        B = dict(corner_radius=7, height=36, font=ctk.CTkFont(size=11, weight="bold"))
        def sep(): ctk.CTkFrame(parent, height=1, fg_color=GUI_BORDER).pack(fill="x", padx=12, pady=7)
        def lbl(t): ctk.CTkLabel(parent, text=t,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=GUI_GRAY).pack(anchor="w", padx=14, pady=(5, 2))

        ctk.CTkFrame(parent, height=12, fg_color="transparent").pack()
        lbl("SESIÓN")
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

        sep(); lbl("BASELINE A↔B (m)")
        self._bl_entry = ctk.CTkEntry(parent, placeholder_text="1.50",
            fg_color=GUI_CARD, border_color=GUI_BORDER, height=32)
        self._bl_entry.insert(0, str(DEFAULT_BASELINE))
        self._bl_entry.pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(parent, text="↺  APLICAR", fg_color=GUI_PANEL,
            text_color=GUI_CYAN, border_color=GUI_CYAN, border_width=1,
            hover_color=GUI_CARD, command=self._cmd_apply_baseline, **B
        ).pack(fill="x", padx=12, pady=2)

        sep()
        self._stereo_lbl = ctk.CTkLabel(parent, text="3D: —/—",
            font=ctk.CTkFont("Courier New", 12, weight="bold"),
            text_color=GUI_GREEN)
        self._stereo_lbl.pack(padx=14, anchor="w")
        self._status_lbl = ctk.CTkLabel(parent, text="",
            font=ctk.CTkFont(size=9), text_color=GUI_GRAY,
            wraplength=145, justify="left")
        self._status_lbl.pack(padx=14, anchor="w", pady=(4, 0))

        sep(); lbl("REGISTRO")
        self._log_box = ctk.CTkTextbox(parent, fg_color=GUI_CARD,
            text_color=GUI_GRAY, font=ctk.CTkFont("Courier New", 8),
            wrap="word", corner_radius=6)
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_center(self, parent):
        # ── 3 cámaras — zona principal expandible ──────────────────
        cam_row = ctk.CTkFrame(parent, fg_color="transparent")
        cam_row.pack(fill="both", expand=True, padx=4, pady=(4, 2))

        self._cam_lbls = []
        cam_defs = [
            ("CAM A  ·  PRINCIPAL", GUI_GREEN),
            ("CAM B  ·  ÁNGULO B",  GUI_MAGENTA),
            ("CAM C  ·  ÁNGULO C",  GUI_CYAN),
        ]
        for title, color in cam_defs:
            f = ctk.CTkFrame(cam_row, fg_color=GUI_CARD, corner_radius=10)
            f.pack(side="left", fill="both", expand=True, padx=3)
            ctk.CTkLabel(f, text=title,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=color).pack(pady=(6, 2))
            lbl = ctk.CTkLabel(f, text="", fg_color=GUI_BLACK)
            lbl.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self._cam_lbls.append(lbl)

        # ── Stats banda inferior ────────────────────────────────────
        stats_bar = ctk.CTkFrame(parent, fg_color=GUI_PANEL, height=195, corner_radius=0)
        stats_bar.pack(fill="x"); stats_bar.pack_propagate(False)

        info = ctk.CTkFrame(stats_bar, fg_color="transparent", height=32)
        info.pack(fill="x", padx=14, pady=(6, 0)); info.pack_propagate(False)
        ctk.CTkLabel(info, text="Rounds:",
            font=ctk.CTkFont(size=10), text_color=GUI_GRAY).pack(side="left")
        self._round_badges = []
        for i in range(TOTAL_ROUNDS):
            b = ctk.CTkLabel(info, text=str(i+1), width=28, height=28,
                font=ctk.CTkFont("Courier New", 11, weight="bold"),
                fg_color=GUI_CARD, text_color=GUI_GRAY, corner_radius=14)
            b.pack(side="left", padx=3)
            self._round_badges.append(b)

        cards = ctk.CTkFrame(stats_bar, fg_color="transparent")
        cards.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self._rc = self._fighter_panel(cards, "ESQUINA ROJA", GUI_RED)
        ctk.CTkFrame(cards, width=2, fg_color=GUI_BORDER).pack(side="left", fill="y", padx=4)
        self._bc = self._fighter_panel(cards, "ESQUINA AZUL", GUI_BLUE)

    def _fighter_panel(self, parent, title, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(f, text=f"● {title}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color).pack(anchor="w", padx=8, pady=(4, 2))
        grid = ctk.CTkFrame(f, fg_color="transparent"); grid.pack(fill="x", padx=4)
        defs = [
            ("strikes",  "GOLPES",  ""),
            ("connected","HITS",    ""),
            ("accuracy", "PREC",    "%"),
            ("face_hits","CARA",    ""),
            ("max_spd",  "VEL MÁX", "m/s"),
            ("max_ext",  "EXT",     "m"),
            ("agility",  "AGIL",    ""),
            ("dodges",   "ESQV",    ""),
            ("score",    "SCORE",   ""),
        ]
        cards = {}
        for i, (k, lb, unit) in enumerate(defs):
            c = StatCard(grid, lb, unit=unit, accent=color)
            c.grid(row=i//5, column=i%5, padx=2, pady=2, sticky="ew")
            grid.columnconfigure(i%5, weight=1); cards[k] = c
        tl = ctk.CTkLabel(f, text="",
            font=ctk.CTkFont("Courier New", 9),
            text_color=GUI_GRAY, justify="left")
        tl.pack(anchor="w", padx=10, pady=(2, 4)); cards['_tl'] = tl
        return cards

    # ── Inicio del engine ──────────────────────────────────────────
    def _detect_and_start(self):
        self._cameras = detect_cameras()
        if not self._cameras:
            self._top_status.configure(text="❌ Sin cámaras", text_color=GUI_RED)
            return

        cam_a = self._cameras[0]['index']
        cam_b = self._cameras[1]['index'] if len(self._cameras) >= 2 else None
        cam_c = self._cameras[2]['index'] if len(self._cameras) >= 3 else None

        labels = "  |  ".join(c['label'] for c in self._cameras)
        self._top_status.configure(text=labels, text_color=GUI_GREEN)

        self._engine = VisionEngine(cam_a, cam_b, cam_c, DEFAULT_BASELINE)
        self._engine.start()
        self._running = True
        self.after(33, self._update_gui)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Loop GUI @ ~30 fps ─────────────────────────────────────────
    def _update_gui(self):
        if not self._running or self._engine is None: return

        fa, fb, fc = self._engine.get_frames()
        stats      = self._engine.get_stats()
        logs       = self._engine.get_logs()

        for lbl, frame in zip(self._cam_lbls, [fa, fb, fc]):
            if frame is not None:
                self._set_frame(lbl, frame)

        if stats:
            rem = stats.get('rem', 0); m2, s2 = rem // 60, rem % 60
            self._timer_lbl.configure(text=f"{m2:02d}:{s2:02d}")
            self._round_lbl.configure(text=f"ROUND {stats.get('rnd', 1)}")

            ph, st = stats.get('phase', 'IDLE'), stats.get('state', 'IDLE')
            ptxt = ("IDLE"     if st == "IDLE" else
                    "PAUSA"    if st == "PAUSED" else
                    "EN VIVO"  if ph == "ROUND" else "DESCANSO")
            pcol = (GUI_GRAY   if st == "IDLE" else
                    GUI_RED    if st == "PAUSED" else
                    GUI_GREEN  if ph == "ROUND" else GUI_YELLOW)
            self._phase_lbl.configure(text=ptxt, text_color=pcol)
            self._top_status.configure(text=stats.get('status_msg', ''), text_color=GUI_GRAY)

            def upd(cards, data):
                for k, c in cards.items():
                    if k == '_tl': continue
                    c.set(data.get(k, '—'))
                pt = data.get('ptypes', {})
                cards['_tl'].configure(
                    text=(f"J:{pt.get('JAB',0)} C:{pt.get('CROSS',0)} "
                          f"H:{pt.get('HOOK',0)} U:{pt.get('UPPERCUT',0)} O:{pt.get('OVERHAND',0)}"))

            upd(self._rc, stats.get('red',  {}))
            upd(self._bc, stats.get('blue', {}))

            rw = stats.get('rnd_winners', {})
            for i, badge in enumerate(self._round_badges):
                w = rw.get(i + 1)
                if   w == "red":  badge.configure(fg_color=GUI_RED,  text_color=GUI_WHITE)
                elif w == "blue": badge.configure(fg_color=GUI_BLUE, text_color=GUI_WHITE)
                elif w == "test": badge.configure(fg_color=GUI_CYAN, text_color=GUI_BG)
                elif w == "draw": badge.configure(fg_color=GUI_GRAY, text_color=GUI_WHITE)
                else:             badge.configure(fg_color=GUI_CARD, text_color=GUI_GRAY)

            n3, nt = stats.get('n_3d', 0), max(stats.get('n_kp', 1), 1)
            self._stereo_lbl.configure(
                text=f"3D: {n3}/{nt}",
                text_color=GUI_GREEN if n3 > 0 else GUI_GRAY)
            self._status_lbl.configure(text=stats.get('status_msg', ''))

        if logs:
            self._log_box.configure(state="normal")
            self._log_box.delete("1.0", "end")
            for msg in logs[-14:]: self._log_box.insert("end", msg + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

        self.after(33, self._update_gui)

    @staticmethod
    def _set_frame(lbl, bgr):
        try:
            lw = lbl.winfo_width(); lh = lbl.winfo_height()
            if lw < 10 or lh < 10: lw, lh = 426, 320
            asp = bgr.shape[1] / bgr.shape[0]
            if lw / lh > asp: lw = int(lh * asp)
            else:              lh = int(lw / asp)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb).resize((lw, lh), Image.BILINEAR)
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(lw, lh))
            lbl.configure(image=img, text=""); lbl._image = img
        except:
            pass

    # ── Comandos ───────────────────────────────────────────────────
    def _cmd_start(self):
        if self._engine and not self._engine.cmd_start():
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

    def _cmd_apply_baseline(self):
        if not self._engine: return
        try:
            bl = float(self._bl_entry.get())
            self._engine.stereo_ab.B = max(0.05, bl)
            self._engine.stereo_ac.B = max(0.05, bl * 1.2)
            self._engine._log(f"Baseline → {bl:.2f}m")
        except:
            pass

    def _on_close(self):
        self._running = False
        if self._engine: self._engine.cmd_stop()
        time.sleep(0.3)
        self.destroy()

# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = FighterIDApp()
    app.mainloop()