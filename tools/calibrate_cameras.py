#!/usr/bin/env python3
"""
FighterID — Camera Calibration Tool
Genera camera_calibration.json para triangulación 3D real (DLT).

USO:
  python tools/calibrate_cameras.py
  python tools/calibrate_cameras.py --cams 0 1 2 --board 9x6 --square 0.025
  python tools/calibrate_cameras.py --load-images ./calib_imgs  # desde imágenes guardadas

CONTROLES durante captura:
  SPACE / S  — Capturar frame actual (si el tablero es detectado)
  U          — Deshacer última captura
  C / ENTER  — Continuar al siguiente paso
  G          — Guardar capturas actuales como imágenes PNG
  Q / ESC    — Cancelar y salir sin guardar

FLUJO COMPLETO:
  Paso 1: Calibración individual de cada cámara (intrínsecas)
  Paso 2: Calibración estéreo par A-B (simultánea)
  Paso 3: Calibración estéreo par A-C (simultánea, si cámara C disponible)
  Paso 4: Guardar camera_calibration.json

BUENAS PRÁCTICAS:
  - Tablero 9×6 (interior), cuadrado de ~25mm
  - ≥20 capturas por cámara, variando ángulo y distancia
  - Para estéreo: tablero visible en AMBAS cámaras al mismo tiempo
  - RMS < 1.0 px = buena calibración; < 0.5 px = excelente
"""

import cv2
import numpy as np
import json
import argparse
import sys
import time
from pathlib import Path

# ── Configuración por defecto ───────────────────────────────────────────
DEFAULT_CAMS        = [0, 1, 2]
DEFAULT_BOARD_COLS  = 9          # esquinas interiores columnas
DEFAULT_BOARD_ROWS  = 6          # esquinas interiores filas
DEFAULT_SQUARE_M    = 0.025      # tamaño de cuadrado en metros (25mm)
MIN_CAPTURES        = 15         # mínimo de capturas para calibrar
TARGET_CAPTURES     = 20         # objetivo recomendado
OUTPUT_FILE         = "camera_calibration.json"

# Criterio de refinamiento de esquinas
CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


# ── Helpers ─────────────────────────────────────────────────────────────

def build_objpoints(rows: int, cols: int, square_m: float) -> np.ndarray:
    """Construye los puntos 3D del tablero (en el plano Z=0)."""
    obj = np.zeros((rows * cols, 3), np.float32)
    obj[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    return obj * square_m


def detect_corners(frame: np.ndarray, rows: int, cols: int) -> tuple:
    """
    Detecta esquinas del tablero en el frame.
    Retorna (found: bool, corners_refined, gray_frame).
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
    if found:
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), CRITERIA)
    return found, corners, gray


def draw_overlay(frame: np.ndarray, found: bool, corners,
                 count: int, target: int, label: str,
                 rows: int, cols: int) -> np.ndarray:
    """Dibuja overlay informativo en el frame."""
    disp = frame.copy()
    h, w = disp.shape[:2]

    if found:
        cv2.drawChessboardCorners(disp, (cols, rows), corners, found)
        color = (0, 255, 0)
        status = f"TABLERO OK — SPACE para capturar ({count}/{target})"
    else:
        color = (0, 100, 255)
        status = f"Buscando tablero... ({count}/{target} capturas)"

    # Barra de progreso
    bar_w = int((count / target) * w)
    cv2.rectangle(disp, (0, h - 8), (w, h), (40, 40, 40), -1)
    cv2.rectangle(disp, (0, h - 8), (bar_w, h), color, -1)

    # Estado y controles
    cv2.putText(disp, f"CAM {label}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(disp, status, (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.putText(disp, "SPACE=capturar  U=deshacer  C=continuar  Q=salir",
                (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    return disp


def open_camera(idx: int, w: int = 1280, h: int = 720) -> cv2.VideoCapture:
    """Abre una cámara con configuración estándar."""
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def collect_single_camera(cap: cv2.VideoCapture, cam_label: str,
                           rows: int, cols: int, objp: np.ndarray,
                           save_dir: Path | None = None) -> tuple:
    """
    Recopila capturas del tablero para una sola cámara.
    Retorna (objpoints, imgpoints, image_size) o (None, None, None) si se cancela.
    """
    objpoints, imgpoints = [], []
    img_size = None

    win = f"Calibración — Cámara {cam_label}"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 960, 540)

    print(f"\n[CAM {cam_label}] Iniciando captura de calibración individual")
    print(f"  Objetivo: {TARGET_CAPTURES} capturas del tablero {cols}×{rows}")
    print(f"  Mueve el tablero a distintos ángulos y distancias\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print(f"[CAM {cam_label}] Error leyendo frame")
            break

        found, corners, gray = detect_corners(frame, rows, cols)
        disp = draw_overlay(frame, found, corners,
                            len(imgpoints), TARGET_CAPTURES,
                            cam_label, rows, cols)
        cv2.imshow(win, disp)

        key = cv2.waitKey(1) & 0xFF

        if key in (ord(' '), ord('s')) and found:
            objpoints.append(objp)
            imgpoints.append(corners)
            img_size = gray.shape[::-1]
            print(f"  ✓ Captura #{len(imgpoints)}")
            if save_dir:
                save_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(save_dir / f"cam{cam_label}_{len(imgpoints):03d}.png"), frame)
            time.sleep(0.3)  # evitar capturas duplicadas

        elif key == ord('u') and imgpoints:
            objpoints.pop()
            imgpoints.pop()
            print(f"  ↩ Captura eliminada — total: {len(imgpoints)}")

        elif key in (ord('c'), 13):  # C o Enter
            if len(imgpoints) < MIN_CAPTURES:
                print(f"  ⚠ Solo {len(imgpoints)} capturas — necesitas al menos {MIN_CAPTURES}")
            else:
                print(f"  → Continuando con {len(imgpoints)} capturas")
                break

        elif key in (ord('q'), 27):  # Q o ESC
            print("  ✗ Calibración cancelada")
            cv2.destroyWindow(win)
            return None, None, None

    cv2.destroyWindow(win)
    return objpoints, imgpoints, img_size


def collect_stereo_pair(cap_a: cv2.VideoCapture, cap_b: cv2.VideoCapture,
                        label_a: str, label_b: str,
                        rows: int, cols: int, objp: np.ndarray,
                        save_dir: Path | None = None) -> tuple:
    """
    Recopila pares de capturas simultáneas para calibración estéreo.
    Retorna (objpoints, imgpoints_a, imgpoints_b, image_size) o Nones si cancela.
    """
    objpoints, imgpoints_a, imgpoints_b = [], [], []
    img_size = None

    win_a = f"Estéreo — Cámara {label_a}"
    win_b = f"Estéreo — Cámara {label_b}"
    cv2.namedWindow(win_a, cv2.WINDOW_NORMAL)
    cv2.namedWindow(win_b, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_a, 720, 405)
    cv2.resizeWindow(win_b, 720, 405)
    cv2.moveWindow(win_a, 0, 0)
    cv2.moveWindow(win_b, 730, 0)

    print(f"\n[ESTÉREO {label_a}-{label_b}] Captura de pares simultáneos")
    print(f"  El tablero debe ser visible en AMBAS cámaras")
    print(f"  Objetivo: {TARGET_CAPTURES} pares válidos\n")

    while True:
        ret_a, frame_a = cap_a.read()
        ret_b, frame_b = cap_b.read()
        if not ret_a or not ret_b:
            break

        found_a, corners_a, gray_a = detect_corners(frame_a, rows, cols)
        found_b, corners_b, gray_b = detect_corners(frame_b, rows, cols)
        both_found = found_a and found_b

        disp_a = draw_overlay(frame_a, found_a, corners_a,
                              len(imgpoints_a), TARGET_CAPTURES,
                              label_a, rows, cols)
        disp_b = draw_overlay(frame_b, found_b, corners_b,
                              len(imgpoints_b), TARGET_CAPTURES,
                              label_b, rows, cols)

        # Indicador de "ambas detectadas"
        if both_found:
            cv2.putText(disp_a, "✓ PAR LISTO", (disp_a.shape[1] - 200, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp_b, "✓ PAR LISTO", (disp_b.shape[1] - 200, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow(win_a, disp_a)
        cv2.imshow(win_b, disp_b)

        key = cv2.waitKey(1) & 0xFF

        if key in (ord(' '), ord('s')) and both_found:
            objpoints.append(objp)
            imgpoints_a.append(corners_a)
            imgpoints_b.append(corners_b)
            img_size = gray_a.shape[::-1]
            print(f"  ✓ Par #{len(imgpoints_a)}")
            if save_dir:
                save_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(save_dir / f"stereo{label_a}{label_b}_a_{len(imgpoints_a):03d}.png"), frame_a)
                cv2.imwrite(str(save_dir / f"stereo{label_a}{label_b}_b_{len(imgpoints_a):03d}.png"), frame_b)
            time.sleep(0.3)

        elif key in (ord(' '), ord('s')) and not both_found:
            print("  ⚠ El tablero no está visible en ambas cámaras")

        elif key == ord('u') and imgpoints_a:
            objpoints.pop(); imgpoints_a.pop(); imgpoints_b.pop()
            print(f"  ↩ Par eliminado — total: {len(imgpoints_a)}")

        elif key in (ord('c'), 13):
            if len(imgpoints_a) < MIN_CAPTURES:
                print(f"  ⚠ Solo {len(imgpoints_a)} pares — necesitas al menos {MIN_CAPTURES}")
            else:
                print(f"  → Continuando con {len(imgpoints_a)} pares")
                break

        elif key in (ord('q'), 27):
            print("  ✗ Calibración estéreo cancelada")
            cv2.destroyAllWindows()
            return None, None, None, None

    cv2.destroyWindow(win_a)
    cv2.destroyWindow(win_b)
    return objpoints, imgpoints_a, imgpoints_b, img_size


def calibrate_single(objpoints: list, imgpoints: list,
                     img_size: tuple, label: str) -> dict | None:
    """Calibra una cámara individual. Retorna dict con K, dist, rms."""
    print(f"\n[CALIBRANDO CAM {label}] {len(objpoints)} capturas...")
    ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, img_size, None, None)
    print(f"  RMS reprojection error: {ret:.4f} px")
    if ret > 2.0:
        print(f"  ⚠ RMS > 2.0 — calibración pobre. Repite con mejores capturas.")
    elif ret < 0.5:
        print(f"  ✓ Excelente calibración (RMS < 0.5)")
    else:
        print(f"  ✓ Calibración aceptable")

    return {
        "K":   K.tolist(),
        "dist": dist.flatten().tolist(),
        "rms":  round(float(ret), 4),
    }


def calibrate_stereo(objpoints: list, imgpoints_a: list, imgpoints_b: list,
                     img_size: tuple, calib_a: dict, calib_b: dict,
                     label_a: str, label_b: str) -> dict | None:
    """
    Calibración estéreo usando las intrínsecas ya calculadas.
    Retorna dict con P1, P2, R, T, baseline_m, rms.
    """
    print(f"\n[CALIBRANDO ESTÉREO {label_a}-{label_b}] {len(objpoints)} pares...")

    K1 = np.array(calib_a["K"], dtype=np.float64)
    d1 = np.array(calib_a["dist"], dtype=np.float64)
    K2 = np.array(calib_b["K"], dtype=np.float64)
    d2 = np.array(calib_b["dist"], dtype=np.float64)

    flags = cv2.CALIB_FIX_INTRINSIC
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)

    ret, K1, d1, K2, d2, R, T, E, F = cv2.stereoCalibrate(
        objpoints, imgpoints_a, imgpoints_b,
        K1, d1, K2, d2, img_size,
        criteria=criteria, flags=flags,
    )
    print(f"  RMS estéreo: {ret:.4f} px")
    if ret > 2.0:
        print(f"  ⚠ RMS estéreo > 2.0 — considera más pares de calibración")
    else:
        print(f"  ✓ Calibración estéreo OK")

    baseline_m = float(np.linalg.norm(T))
    print(f"  Baseline estimado: {baseline_m:.3f} m")

    # Rectificación estéreo — obtiene P1, P2
    R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
        K1, d1, K2, d2, img_size, R, T, alpha=0)

    return {
        "P1":         P1.tolist(),
        "P2":         P2.tolist(),
        "R":          R.tolist(),
        "T":          T.flatten().tolist(),
        "R1":         R1.tolist(),
        "R2":         R2.tolist(),
        "Q":          Q.tolist(),
        "baseline_m": round(baseline_m, 4),
        "rms":        round(float(ret), 4),
    }


def save_calibration(result: dict, output_path: str) -> None:
    """Guarda la calibración en JSON."""
    path = Path(output_path)
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[GUARDADO] {path.resolve()}")
    print("  Coloca este archivo en la raíz del proyecto para activar triangulación DLT")


def print_summary(result: dict) -> None:
    """Imprime resumen de la calibración."""
    print("\n" + "="*60)
    print("  RESUMEN DE CALIBRACIÓN")
    print("="*60)
    for cam, data in result.get("cameras", {}).items():
        print(f"  Cámara {cam}: RMS={data['rms']:.4f}px")
    for pair, data in result.get("stereo", {}).items():
        print(f"  Estéreo {pair}: RMS={data['rms']:.4f}px  "
              f"baseline={data['baseline_m']:.3f}m")
    print("="*60)
    print("\n  Uso con triangulación DLT:")
    print("  Los datos de 'stereo.AB.P1/P2' se usan automáticamente")
    print("  cuando camera_calibration.json está en la raíz del proyecto.")


# ── Modo de carga desde imágenes guardadas ──────────────────────────────

def load_images_from_dir(img_dir: Path, pattern: str,
                         rows: int, cols: int, objp: np.ndarray) -> tuple:
    """Carga imágenes guardadas y detecta esquinas."""
    files = sorted(img_dir.glob(pattern))
    if not files:
        return None, None, None
    objpoints, imgpoints, img_size = [], [], None
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        found, corners, gray = detect_corners(img, rows, cols)
        if found:
            objpoints.append(objp)
            imgpoints.append(corners)
            img_size = gray.shape[::-1]
    print(f"  {len(objpoints)} capturas válidas encontradas en {img_dir}")
    return objpoints, imgpoints, img_size


# ── Programa principal ──────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Calibración de cámaras para FighterID Vision")
    p.add_argument("--cams",   nargs="+", type=int, default=DEFAULT_CAMS,
                   help="Índices de cámaras (default: 0 1 2)")
    p.add_argument("--board",  default=f"{DEFAULT_BOARD_COLS}x{DEFAULT_BOARD_ROWS}",
                   help="Tamaño tablero ColsxFilas (default: 9x6)")
    p.add_argument("--square", type=float, default=DEFAULT_SQUARE_M,
                   help="Tamaño del cuadrado en metros (default: 0.025)")
    p.add_argument("--output", default=OUTPUT_FILE,
                   help="Archivo de salida (default: camera_calibration.json)")
    p.add_argument("--save-images", action="store_true",
                   help="Guardar imágenes de calibración en ./calib_imgs/")
    p.add_argument("--load-images", type=str, default=None,
                   help="Cargar calibración desde imágenes guardadas en DIRECTORIO")
    p.add_argument("--skip-stereo", action="store_true",
                   help="Calibrar solo intrínsecas individuales, sin estéreo")
    p.add_argument("--resolution", default="1280x720",
                   help="Resolución de cámara (default: 1280x720)")
    return p.parse_args()


def main():
    args = parse_args()

    # Parsear board size
    cols_str, rows_str = args.board.lower().split("x")
    board_cols, board_rows = int(cols_str), int(rows_str)
    objp = build_objpoints(board_rows, board_cols, args.square)

    # Resolución
    cam_w, cam_h = map(int, args.resolution.lower().split("x"))

    save_dir = Path("calib_imgs") if args.save_images else None

    print("="*60)
    print("  FIGHTERID — CALIBRACIÓN DE CÁMARAS")
    print("="*60)
    print(f"  Tablero: {board_cols}×{board_rows} esquinas  |  Cuadrado: {args.square*100:.1f}cm")
    print(f"  Cámaras: {args.cams}")
    print(f"  Salida:  {args.output}")
    print()

    result = {
        "version":    1,
        "chessboard": {"rows": board_rows, "cols": board_cols, "square_m": args.square},
        "image_size": [cam_w, cam_h],
        "cameras":    {},
        "stereo":     {},
    }

    # ── FASE 1: Calibración individual ─────────────────────────────────
    caps = {}
    cam_labels = ["A", "B", "C"]
    cam_data   = {}   # label → (objpoints, imgpoints, img_size)

    if args.load_images:
        img_base = Path(args.load_images)
        print("[MODO IMÁGENES] Cargando desde directorio guardado")
        for i, idx in enumerate(args.cams):
            label = cam_labels[i]
            ops, ips, isz = load_images_from_dir(
                img_base, f"cam{label}_*.png", board_rows, board_cols, objp)
            if ops:
                cam_data[label] = (ops, ips, isz)
    else:
        # Abrir cámaras
        for i, idx in enumerate(args.cams):
            label = cam_labels[i]
            cap = open_camera(idx, cam_w, cam_h)
            if cap is None:
                print(f"[AVISO] Cámara {label} (idx={idx}) no disponible — omitida")
                continue
            caps[label] = cap
            print(f"[CAM {label}] Abierta en índice {idx}")

        if "A" not in caps:
            print("[ERROR] Cámara A (principal) no disponible — abortando")
            sys.exit(1)

        # Calibrar cada cámara individualmente
        for label, cap in caps.items():
            ops, ips, isz = collect_single_camera(
                cap, label, board_rows, board_cols, objp, save_dir)
            if ops is None:
                print(f"[ABORTADO] Calibración cancelada en cámara {label}")
                for c in caps.values():
                    c.release()
                sys.exit(0)
            cam_data[label] = (ops, ips, isz)

    # Calcular intrínsecas
    calibrations = {}
    for label, (ops, ips, isz) in cam_data.items():
        calib = calibrate_single(ops, ips, isz, label)
        if calib:
            calibrations[label] = calib
            result["cameras"][label] = calib

    if not calibrations:
        print("[ERROR] Sin calibraciones válidas")
        sys.exit(1)

    # ── FASE 2: Calibración estéreo ─────────────────────────────────────
    if not args.skip_stereo and len(calibrations) >= 2:
        stereo_pairs = []
        if "A" in calibrations and "B" in calibrations:
            stereo_pairs.append(("A", "B"))
        if "A" in calibrations and "C" in calibrations:
            stereo_pairs.append(("A", "C"))

        for la, lb in stereo_pairs:
            pair_key = f"{la}{lb}"
            if args.load_images:
                img_base = Path(args.load_images)
                ops_s  = []
                ips_la, ips_lb = [], []
                # Buscar pares de imágenes
                files_a = sorted(img_base.glob(f"stereo{pair_key}_a_*.png"))
                files_b = sorted(img_base.glob(f"stereo{pair_key}_b_*.png"))
                isz_s   = None
                for fa, fb in zip(files_a, files_b):
                    ima = cv2.imread(str(fa)); imb = cv2.imread(str(fb))
                    if ima is None or imb is None:
                        continue
                    fnd_a, co_a, gr_a = detect_corners(ima, board_rows, board_cols)
                    fnd_b, co_b, gr_b = detect_corners(imb, board_rows, board_cols)
                    if fnd_a and fnd_b:
                        ops_s.append(objp); ips_la.append(co_a); ips_lb.append(co_b)
                        isz_s = gr_a.shape[::-1]
                print(f"  {len(ops_s)} pares válidos para {pair_key}")
                stereo_ok = len(ops_s) >= MIN_CAPTURES
            else:
                cap_a = caps.get(la)
                cap_b = caps.get(lb)
                if cap_a is None or cap_b is None:
                    continue
                ops_s, ips_la, ips_lb, isz_s = collect_stereo_pair(
                    cap_a, cap_b, la, lb, board_rows, board_cols, objp, save_dir)
                stereo_ok = ops_s is not None and len(ops_s) >= MIN_CAPTURES

            if stereo_ok:
                stereo_calib = calibrate_stereo(
                    ops_s, ips_la, ips_lb, isz_s,
                    calibrations[la], calibrations[lb], la, lb)
                if stereo_calib:
                    result["stereo"][pair_key] = stereo_calib

    # Cerrar cámaras
    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()

    # ── FASE 3: Guardar resultados ──────────────────────────────────────

    # Para compatibilidad con el loader actual de three_camera_ui.py,
    # poner P1/P2 del par AB también en la raíz del JSON
    if "AB" in result["stereo"]:
        result["P1"] = result["stereo"]["AB"]["P1"]
        result["P2"] = result["stereo"]["AB"]["P2"]
    elif result["cameras"]:
        # Sin estéreo: construir matrices de proyección desde intrínsecas
        # Asume cámaras alineadas horizontalmente
        first_cam = list(result["cameras"].values())[0]
        K = np.array(first_cam["K"])
        P1 = np.hstack([K, np.zeros((3, 1))])
        result["P1"] = P1.tolist()
        print("[AVISO] Sin calibración estéreo — P1/P2 son estimaciones")

    save_calibration(result, args.output)
    print_summary(result)


if __name__ == "__main__":
    # Compatibilidad con args.cam vs args.cams
    import sys
    args_raw = sys.argv[1:]
    main()
