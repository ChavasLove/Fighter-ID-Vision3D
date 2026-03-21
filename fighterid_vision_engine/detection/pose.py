"""
FighterID Vision Engine — PoseDetector
Detección YOLOv8-pose con ONNX + DirectML como backend principal.
Fallback automático a ultralytics si onnxruntime no está instalado.
Extraído de vision_motor_v1.py.
"""

import os

import cv2
import numpy as np

# ── GPU detection (heredado del entorno raíz) ──────────────────────────
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
        if torch.cuda.is_available():
            _DEVICE = "cuda"
            print(f"[GPU] CUDA: {torch.cuda.get_device_name(0)}")
        else:
            print("[GPU] Sin GPU acelerada — usando CPU")
    except ImportError:
        print("[GPU] torch no disponible — usando CPU")

# Rutas de modelo: busca primero en la carpeta models/ del paquete,
# luego en el directorio de trabajo (raíz del repo) como fallback.
_PKG_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_DIR = os.path.join(_PKG_DIR, "models")


def _find_model(filename: str) -> str:
    """Devuelve la ruta del modelo buscando en models/ y luego en cwd."""
    pkg_path = os.path.join(_MODEL_DIR, filename)
    if os.path.exists(pkg_path):
        return pkg_path
    cwd_path = filename  # relativo al cwd (raíz del repo)
    if os.path.exists(cwd_path):
        return cwd_path
    return filename  # deja que YOLO/onnxruntime falle con mensaje claro


class PoseDetector:
    """
    Detección de pose YOLOv8-pose.
    Prioridad: onnxruntime-directml → ultralytics (con DirectML/CUDA).
    Si yolov8n-pose.onnx no existe, lo exporta automáticamente desde el .pt.
    """

    ONNX_FILENAME = "yolov8n-pose.onnx"
    PT_FILENAME   = "yolov8n-pose.pt"
    CONF_THR      = 0.45

    def __init__(self):
        self._ort_session = None
        self._yolo        = None
        self._input_name  = None
        self._init()

    def _init(self) -> None:
        onnx_path = _find_model(self.ONNX_FILENAME)
        pt_path   = _find_model(self.PT_FILENAME)

        # ── Intento 1: onnxruntime-directml ──────────────────────────
        try:
            import onnxruntime as ort
            if not os.path.exists(onnx_path):
                self._export_onnx(pt_path, onnx_path)
            providers = (["DmlExecutionProvider"]
                         if _DEVICE in ("dml", "cuda")
                         else ["CPUExecutionProvider"])
            self._ort_session = ort.InferenceSession(onnx_path, providers=providers)
            self._input_name  = self._ort_session.get_inputs()[0].name
            print(f"[ONNX] Cargado — providers={providers}")
            return
        except ImportError:
            print("[ONNX] onnxruntime no instalado — "
                  "instala: pip install onnxruntime-directml")
        except Exception as e:
            print(f"[ONNX] Error al cargar: {e}")

        # ── Fallback: ultralytics ─────────────────────────────────────
        self._init_ultralytics(pt_path)

    def _export_onnx(self, pt_path: str, onnx_path: str) -> None:
        print(f"[ONNX] Exportando {pt_path} → {onnx_path}…")
        from ultralytics import YOLO
        m = YOLO(pt_path)
        m.export(format="onnx", imgsz=640, opset=12, simplify=True)
        print("[ONNX] Exportación completa")

    def _init_ultralytics(self, pt_path: str) -> None:
        from ultralytics import YOLO
        self._yolo = YOLO(pt_path)
        if _DEVICE == "dml" and _DML_DEV is not None:
            self._yolo.to(_DML_DEV)
        elif _DEVICE == "cuda":
            self._yolo.to("cuda")
        print(f"[YOLO] Modelo cargado — device={_DEVICE}  path={pt_path}")

    # ── Inferencia ────────────────────────────────────────────────────

    def infer(self, frame: np.ndarray) -> list:
        """
        Retorna lista de dicts por persona detectada:
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
        data   = output[0]
        if data.ndim == 2 and data.shape[0] == 56:
            data = data.T  # → [N, 56]

        persons = []
        for det in data:
            conf = float(det[4])
            if conf < self.CONF_THR:
                continue
            cx, cy, w, h = det[0]*sx, det[1]*sy, det[2]*sx, det[3]*sy
            x1, y1, x2, y2 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
            kps_raw       = det[5:].reshape(17, 3).copy()
            kps_raw[:, 0] *= sx
            kps_raw[:, 1] *= sy
            persons.append({"keypoints": kps_raw, "bbox": [x1, y1, x2, y2], "conf": conf})
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
        boxes = r.boxes.xyxy.cpu().numpy() if r.boxes is not None else []
        for i in range(len(kps_xy)):
            kps        = np.zeros((17, 3))
            kps[:, :2] = kps_xy[i]
            kps[:, 2]  = kps_conf[i]
            bbox = boxes[i].tolist() if i < len(boxes) else [0, 0, 0, 0]
            persons.append({"keypoints": kps, "bbox": bbox, "conf": 1.0})
        return persons
