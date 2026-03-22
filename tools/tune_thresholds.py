#!/usr/bin/env python3
"""
FighterID — Threshold Tuner
Analiza videos reales para calibrar STRIKE_ACCEL_THRESHOLD y TEMPORAL_WINDOW_FRAMES.

USO:
  # Analizar sin anotaciones (modo exploración):
  python tools/tune_thresholds.py --video fight_001.mp4

  # Analizar con anotaciones (modo evaluación — precisión/recall):
  python tools/tune_thresholds.py --video fight_001.mp4 \\
      --annotations annotations/fight_001_annotations.json

  # Busqueda de rejilla automática (requiere anotaciones):
  python tools/tune_thresholds.py --video fight_001.mp4 \\
      --annotations annotations/fight_001_annotations.json \\
      --grid-search

  # Procesar múltiples videos:
  python tools/tune_thresholds.py --video *.mp4 --annotations annotations/

SALIDA:
  - Distribución de velocidades y aceleraciones detectadas
  - Recomendación de umbrales óptimos
  - (con anotaciones) Precision/Recall/F1 por combinación de umbrales
  - Sección .env lista para copiar/pegar

NOTAS:
  - Este script NO requiere cámaras físicas — solo videos grabados
  - Usa el mismo TemporalStrikeAnalyzer del sistema de producción
  - Los resultados dependen de la calidad del modelo YOLO y del encuadre
"""

import sys
import os
import json
import time
import argparse
import numpy as np
from pathlib import Path
from collections import defaultdict
import cv2

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fighterid_vision_engine.detection.pose import PoseDetector
from fighterid_vision_engine.detection.tracker import PersistentTracker
from fighterid_vision_engine.pipeline.temporal_strike import TemporalStrikeAnalyzer
from fighterid_vision_engine.config.settings import (
    STRIKE_SPEED_MS, STRIKE_ACCEL_THRESHOLD, TEMPORAL_WINDOW_FRAMES,
    STRIKE_COOL_S, PIX_PER_M
)

# ── Configuración de búsqueda de rejilla ────────────────────────────────
GRID_SPEED_VALUES  = [2.5, 3.0, 3.5, 4.0, 5.0]        # m/s
GRID_ACCEL_VALUES  = [10.0, 15.0, 20.0, 25.0, 35.0]    # m/s²
GRID_WINDOW_VALUES = [10, 12, 15, 18, 20]               # frames
GRID_COOL_VALUES   = [0.3, 0.5, 0.7]                    # segundos


# ── Helpers de visualización ────────────────────────────────────────────

def bar_chart_text(values: list[float], bins: int = 20, width: int = 50) -> str:
    """Histograma de texto para visualizar distribuciones."""
    if not values:
        return "  (sin datos)"
    arr = np.array(values)
    counts, edges = np.histogram(arr, bins=bins)
    max_c = max(counts) if counts.max() > 0 else 1
    lines = []
    for i, (c, e) in enumerate(zip(counts, edges)):
        bar = "#" * int(c / max_c * width)
        lines.append(f"  {e:6.2f} | {bar:<{width}} {c:4d}")
    lines.append(f"  {'':6} | min={arr.min():.2f}  p25={np.percentile(arr,25):.2f}  "
                 f"median={np.median(arr):.2f}  p75={np.percentile(arr,75):.2f}  "
                 f"max={arr.max():.2f}")
    return "\n".join(lines)


def compute_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


# ── Procesamiento de video ───────────────────────────────────────────────

def process_video(video_path: str,
                  speed_thr: float   = STRIKE_SPEED_MS,
                  accel_thr: float   = STRIKE_ACCEL_THRESHOLD,
                  window:    int     = TEMPORAL_WINDOW_FRAMES,
                  cool_s:    float   = STRIKE_COOL_S,
                  max_frames: int    = 0,
                  verbose:    bool   = True) -> dict:
    """
    Procesa un video con el TemporalStrikeAnalyzer y recopila estadísticas.

    Retorna dict con:
      detections: list de {frame, corner, speed, conf, punch_type, timestamp}
      wrist_velocities: list de todos los valores de velocidad detectados
      wrist_accels: list de todas las aceleraciones
      fps_avg: FPS promedio de procesamiento
      total_frames: número total de frames procesados
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se puede abrir: {video_path}")

    vid_fps    = cap.get(cv2.CAP_PROP_FPS) or 30
    total_vid  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    detector = PoseDetector()
    tracker  = PersistentTracker()
    analyzer = TemporalStrikeAnalyzer()
    # Sobreescribir umbrales para esta ejecución
    analyzer._vel_thr   = speed_thr
    analyzer._accel_thr = accel_thr
    analyzer._cool_s    = cool_s

    detections       = []
    wrist_velocities = []
    frame_idx        = 0
    t0               = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if max_frames > 0 and frame_idx >= max_frames:
            break

        persons = detector.infer(frame)
        roles   = tracker.assign(persons)
        ts      = frame_idx / vid_fps

        for corner in ("red", "blue"):
            person   = roles.get(corner)
            opponent = roles.get("blue" if corner == "red" else "red")
            if person is None:
                continue

            # Recopilar velocidades de muñeca (independientemente de si es golpe)
            kps = person["keypoints"]
            lw_buf = analyzer._lw.get(corner)
            rw_buf = analyzer._rw.get(corner)
            if lw_buf and len(lw_buf) > 1:
                vels = lw_buf.velocities()
                wrist_velocities.extend(vels)
            if rw_buf and len(rw_buf) > 1:
                vels = rw_buf.velocities()
                wrist_velocities.extend(vels)

            hit, speed, conf, punch_type = analyzer.detect(corner, person, opponent)
            if hit:
                detections.append({
                    "frame":      frame_idx,
                    "timestamp":  round(ts, 3),
                    "corner":     corner,
                    "speed_ms":   round(speed, 3),
                    "confidence": round(conf, 3),
                    "punch_type": punch_type,
                })

        frame_idx += 1
        if verbose and frame_idx % 100 == 0:
            elapsed = time.time() - t0
            proc_fps = frame_idx / elapsed if elapsed > 0 else 0
            pct = frame_idx / total_vid * 100 if total_vid > 0 else 0
            print(f"  Frame {frame_idx}/{total_vid} ({pct:.0f}%)  "
                  f"— {proc_fps:.1f} FPS proc  — {len(detections)} golpes detectados",
                  end="\r")

    cap.release()
    elapsed  = time.time() - t0
    fps_avg  = frame_idx / elapsed if elapsed > 0 else 0

    if verbose:
        print()

    return {
        "detections":       detections,
        "wrist_velocities": wrist_velocities,
        "fps_avg":          fps_avg,
        "total_frames":     frame_idx,
        "vid_fps":          vid_fps,
    }


# ── Evaluación contra anotaciones ──────────────────────────────────────

def load_annotations(ann_path: str) -> list[dict]:
    """Carga anotaciones generadas por annotate_dataset.py."""
    with open(ann_path) as f:
        data = json.load(f)
    return data.get("annotations", [])


def match_detections(detections: list[dict], annotations: list[dict],
                     vid_fps: float, tolerance_frames: int = 10) -> tuple[int, int, int]:
    """
    Compara detecciones con anotaciones ground-truth.

    Una detección es TP si:
      - El frame cae dentro de [ann.frame_start - tol, ann.frame_end + tol]
      - El corner coincide (si la anotación especifica fighter)

    Retorna (tp, fp, fn).
    """
    tol = tolerance_frames
    matched_anns = set()
    tp = fp = 0

    for det in detections:
        matched = False
        for i, ann in enumerate(annotations):
            if i in matched_anns:
                continue
            # Ventana temporal
            in_window = (ann["frame_start"] - tol <= det["frame"]
                         <= ann["frame_end"] + tol)
            # Fighter (si está especificado)
            fighter_ok = (ann.get("fighter") is None or
                          ann.get("fighter") == det["corner"] or
                          ann.get("fighter") == "any")
            if in_window and fighter_ok:
                matched = True
                matched_anns.add(i)
                tp += 1
                break
        if not matched:
            fp += 1

    fn = len(annotations) - len(matched_anns)
    return tp, fp, fn


# ── Búsqueda de rejilla ─────────────────────────────────────────────────

def grid_search(video_path: str, annotations: list[dict],
                vid_fps: float, max_frames: int = 0) -> dict:
    """
    Prueba todas las combinaciones de umbrales y retorna la mejor.
    """
    total_combos = (len(GRID_SPEED_VALUES) * len(GRID_ACCEL_VALUES) *
                    len(GRID_WINDOW_VALUES) * len(GRID_COOL_VALUES))
    print(f"\n  Búsqueda de rejilla: {total_combos} combinaciones...")

    best = {"f1": 0.0, "config": {}}
    results = []
    combo_n  = 0

    for speed in GRID_SPEED_VALUES:
        for accel in GRID_ACCEL_VALUES:
            for window in GRID_WINDOW_VALUES:
                for cool in GRID_COOL_VALUES:
                    combo_n += 1
                    data = process_video(
                        video_path, speed_thr=speed, accel_thr=accel,
                        window=window, cool_s=cool,
                        max_frames=max_frames, verbose=False)

                    tp, fp, fn = match_detections(
                        data["detections"], annotations, vid_fps)
                    prec, rec, f1 = compute_f1(tp, fp, fn)

                    entry = {
                        "speed": speed, "accel": accel,
                        "window": window, "cool": cool,
                        "tp": tp, "fp": fp, "fn": fn,
                        "precision": round(prec, 3),
                        "recall":    round(rec,  3),
                        "f1":        round(f1,   3),
                    }
                    results.append(entry)

                    if f1 > best["f1"]:
                        best = {"f1": f1, "config": entry.copy()}

                    if combo_n % 10 == 0:
                        print(f"  {combo_n}/{total_combos}  best_f1={best['f1']:.3f}",
                              end="\r")

    print(f"\n  Búsqueda completada")

    # Top 5 resultados
    top5 = sorted(results, key=lambda x: x["f1"], reverse=True)[:5]
    return {"best": best, "top5": top5, "all": results}


# ── Informe de salida ────────────────────────────────────────────────────

def print_report(video_path: str, data: dict,
                 annotations: list | None = None,
                 grid_results: dict | None = None) -> None:
    """Imprime el informe completo de análisis."""
    print("\n" + "="*65)
    print("  FIGHTERID — ANÁLISIS DE UMBRALES")
    print("="*65)
    print(f"\n  Video: {Path(video_path).name}")
    print(f"  Frames procesados: {data['total_frames']}  "
          f"({data['vid_fps']:.1f} FPS video  |  {data['fps_avg']:.1f} FPS proceso)")
    print(f"  Golpes detectados: {len(data['detections'])}")

    print(f"\n{'─'*65}")
    print("  UMBRALES ACTUALES:")
    print(f"  STRIKE_SPEED_MS       = {STRIKE_SPEED_MS}")
    print(f"  STRIKE_ACCEL_THRESHOLD= {STRIKE_ACCEL_THRESHOLD}")
    print(f"  TEMPORAL_WINDOW_FRAMES= {TEMPORAL_WINDOW_FRAMES}")
    print(f"  STRIKE_COOL_S         = {STRIKE_COOL_S}")

    # Distribución de velocidades
    vels = [v for v in data["wrist_velocities"] if v > 0.1]
    if vels:
        arr = np.array(vels)
        print(f"\n{'─'*65}")
        print("  DISTRIBUCIÓN DE VELOCIDADES DE MUÑECA (m/s)")
        print(bar_chart_text(vels, bins=15))
        print(f"\n  % movimientos sobre umbral actual ({STRIKE_SPEED_MS} m/s): "
              f"{sum(1 for v in vels if v >= STRIKE_SPEED_MS)/len(vels)*100:.1f}%")
        print(f"  Sugerencia de umbral (percentil 85): "
              f"{np.percentile(arr, 85):.2f} m/s")

    # Distribuciones de golpes detectados
    if data["detections"]:
        speeds = [d["speed_ms"] for d in data["detections"]]
        punch_types = defaultdict(int)
        for d in data["detections"]:
            punch_types[d["punch_type"] or "unknown"] += 1

        print(f"\n{'─'*65}")
        print("  VELOCIDADES DE GOLPES DETECTADOS (m/s)")
        print(bar_chart_text(speeds, bins=10))

        print(f"\n  TIPOS DE GOLPES:")
        total = len(data["detections"])
        for pt, cnt in sorted(punch_types.items(), key=lambda x: -x[1]):
            print(f"    {pt:<12} {cnt:4d} ({cnt/total*100:.0f}%)")

    # Evaluación con anotaciones
    if annotations is not None and data["detections"]:
        tp, fp, fn = match_detections(
            data["detections"], annotations, data["vid_fps"])
        prec, rec, f1 = compute_f1(tp, fp, fn)
        print(f"\n{'─'*65}")
        print("  EVALUACIÓN vs ANOTACIONES GROUND TRUTH")
        print(f"  Anotaciones: {len(annotations)} golpes")
        print(f"  TP={tp}  FP={fp}  FN={fn}")
        print(f"  Precisión:  {prec*100:.1f}%")
        print(f"  Recall:     {rec*100:.1f}%")
        print(f"  F1 Score:   {f1:.3f}")

    # Resultados búsqueda de rejilla
    if grid_results:
        best = grid_results["best"]
        top5 = grid_results["top5"]
        print(f"\n{'─'*65}")
        print("  BÚSQUEDA DE REJILLA — TOP 5 CONFIGURACIONES")
        print(f"  {'Speed':>8} {'Accel':>8} {'Window':>8} {'Cool':>6} "
              f"{'Prec':>7} {'Rec':>7} {'F1':>7}")
        print("  " + "-"*58)
        for r in top5:
            print(f"  {r['speed']:8.1f} {r['accel']:8.1f} {r['window']:8d} "
                  f"{r['cool']:6.1f} {r['precision']:7.3f} {r['recall']:7.3f} {r['f1']:7.3f}")

        bc = best["config"]
        print(f"\n  ✓ MEJOR CONFIGURACIÓN (F1={bc['f1']:.3f}):")
        print(f"    STRIKE_SPEED_MS        = {bc['speed']}")
        print(f"    STRIKE_ACCEL_THRESHOLD = {bc['accel']}")
        print(f"    TEMPORAL_WINDOW_FRAMES = {bc['window']}")
        print(f"    STRIKE_COOL_S          = {bc['cool']}")

    # Recomendaciones automáticas (sin anotaciones)
    elif vels and not annotations:
        arr = np.array(vels)
        rec_speed = round(float(np.percentile(arr, 85)), 1)
        print(f"\n{'─'*65}")
        print("  RECOMENDACIÓN AUTOMÁTICA (sin anotaciones)")
        print(f"  Basada en percentil 85 de velocidades observadas:")
        rec_speed = max(rec_speed, 2.0)   # mínimo razonable
        print(f"\n  STRIKE_SPEED_MS        = {rec_speed}")
        print(f"  STRIKE_ACCEL_THRESHOLD = 15.0  # punto de partida conservador")
        print(f"  TEMPORAL_WINDOW_FRAMES = 12")
        print(f"  STRIKE_COOL_S          = 0.4")

    print(f"\n{'─'*65}")
    print("  BLOQUE .ENV LISTO PARA COPIAR:")

    if grid_results:
        bc = grid_results["best"]["config"]
        env_speed  = bc["speed"]
        env_accel  = bc["accel"]
        env_window = bc["window"]
        env_cool   = bc["cool"]
    elif vels:
        arr = np.array(vels)
        env_speed  = max(round(float(np.percentile(arr, 85)), 1), 2.0)
        env_accel  = 15.0
        env_window = 12
        env_cool   = 0.4
    else:
        env_speed  = STRIKE_SPEED_MS
        env_accel  = STRIKE_ACCEL_THRESHOLD
        env_window = TEMPORAL_WINDOW_FRAMES
        env_cool   = STRIKE_COOL_S

    print(f"""
  STRIKE_SPEED_MS={env_speed}
  STRIKE_ACCEL_THRESHOLD={env_accel}
  TEMPORAL_WINDOW_FRAMES={env_window}
  STRIKE_COOL_S={env_cool}
""")
    print("="*65)


def save_results(data: dict, video_path: str,
                 grid_results: dict | None = None) -> None:
    """Guarda resultados en JSON para uso posterior."""
    out = {
        "video":            video_path,
        "total_frames":     data["total_frames"],
        "vid_fps":          data["vid_fps"],
        "detections":       data["detections"],
        "grid_results":     grid_results,
        "config_used": {
            "STRIKE_SPEED_MS":        STRIKE_SPEED_MS,
            "STRIKE_ACCEL_THRESHOLD": STRIKE_ACCEL_THRESHOLD,
            "TEMPORAL_WINDOW_FRAMES": TEMPORAL_WINDOW_FRAMES,
            "STRIKE_COOL_S":          STRIKE_COOL_S,
        },
    }
    out_path = Path(video_path).with_suffix("_threshold_analysis.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Resultados guardados en: {out_path}")


# ── CLI ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Análisis de umbrales para FighterID TemporalStrikeAnalyzer")
    p.add_argument("--video",  required=True, nargs="+",
                   help="Video(s) a analizar (.mp4, .avi, etc.)")
    p.add_argument("--annotations", nargs="*", default=None,
                   help="Archivo(s) JSON de anotaciones (mismo orden que --video)")
    p.add_argument("--grid-search", action="store_true",
                   help="Busqueda de rejilla sobre umbrales (lento, requiere --annotations)")
    p.add_argument("--max-frames", type=int, default=0,
                   help="Máximo de frames a procesar (0=todo)")
    p.add_argument("--save", action="store_true",
                   help="Guardar resultados en JSON")
    p.add_argument("--plot", action="store_true",
                   help="Generar gráficas (requiere matplotlib)")
    return p.parse_args()


def plot_distributions(data: dict) -> None:
    """Genera gráficas si matplotlib está disponible."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib no disponible — omitiendo gráficas")
        return

    vels = [v for v in data["wrist_velocities"] if v > 0.1]
    det_speeds = [d["speed_ms"] for d in data["detections"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("FighterID — Análisis de Velocidades", fontsize=14)

    # Histograma de todas las velocidades
    axes[0].hist(vels, bins=40, color="#2196F3", edgecolor="white", alpha=0.8)
    axes[0].axvline(STRIKE_SPEED_MS, color="red", linestyle="--",
                    label=f"Umbral actual ({STRIKE_SPEED_MS} m/s)")
    if vels:
        p85 = np.percentile(vels, 85)
        axes[0].axvline(p85, color="orange", linestyle=":",
                        label=f"Percentil 85 ({p85:.2f} m/s)")
    axes[0].set_xlabel("Velocidad (m/s)")
    axes[0].set_ylabel("Frecuencia")
    axes[0].set_title("Todas las velocidades de muñeca")
    axes[0].legend()
    axes[0].set_yscale("log")

    # Histograma de velocidades de golpes detectados
    if det_speeds:
        axes[1].hist(det_speeds, bins=20, color="#4CAF50", edgecolor="white", alpha=0.8)
        axes[1].set_xlabel("Velocidad (m/s)")
        axes[1].set_ylabel("Frecuencia")
        axes[1].set_title(f"Velocidades de golpes detectados (N={len(det_speeds)})")

    plt.tight_layout()
    out_path = "threshold_analysis.png"
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"  Gráfica guardada en: {out_path}")
    try:
        plt.show()
    except Exception:
        pass


def main():
    args = parse_args()

    for i, video_path in enumerate(args.video):
        if not Path(video_path).exists():
            print(f"[ERROR] Video no encontrado: {video_path}")
            continue

        print(f"\n[PROCESANDO] {video_path}")
        data = process_video(video_path, max_frames=args.max_frames, verbose=True)

        annotations = None
        if args.annotations:
            ann_path = args.annotations[i] if i < len(args.annotations) else None
            if ann_path and Path(ann_path).exists():
                annotations = load_annotations(ann_path)
                print(f"  Anotaciones: {len(annotations)} golpes cargados")

        grid_results = None
        if args.grid_search:
            if annotations is None:
                print("  ⚠ --grid-search requiere --annotations — omitido")
            else:
                grid_results = grid_search(
                    video_path, annotations, data["vid_fps"],
                    max_frames=args.max_frames)

        print_report(video_path, data, annotations, grid_results)

        if args.save:
            save_results(data, video_path, grid_results)

        if args.plot:
            plot_distributions(data)


if __name__ == "__main__":
    main()
