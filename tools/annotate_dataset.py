#!/usr/bin/env python3
"""
FighterID — Dataset Annotation Tool
Herramienta visual para anotar golpes en videos de boxeo.

USO:
  python tools/annotate_dataset.py --video fight_001.mp4
  python tools/annotate_dataset.py --video fight_001.mp4 --output my_annotations.json
  python tools/annotate_dataset.py --video fight_001.mp4 --eval  # ver detecciones automáticas

CONTROLES:
  SPACE          — Play / Pausa
  ← / →          — Frame anterior / siguiente (en pausa)
  Shift+← / →    — Saltar 30 frames
  A              — Marcar inicio del golpe (frame actual)
  E              — Marcar fin del golpe (frame actual)
  J              — Tipo: JAB
  C              — Tipo: CROSS
  H              — Tipo: HOOK
  U              — Tipo: UPPERCUT
  R              — Asignar a luchador ROJO
  B              — Asignar a luchador AZUL
  ENTER/RETURN   — Confirmar anotación actual
  Del/Backspace  — Eliminar última anotación
  S              — Guardar
  Q / ESC        — Guardar y salir

FORMATO JSON DE SALIDA:
  {
    "video": "ruta/al/video.mp4",
    "fps": 30,
    "total_frames": 5400,
    "annotations": [
      {
        "id": 1,
        "frame_start": 145,
        "frame_end": 158,
        "fighter": "red",
        "wrist": "right",
        "type": "cross",
        "speed_estimate_ms": null,
        "notes": ""
      }
    ]
  }

FLUJO RECOMENDADO:
  1. Reproducir video (SPACE)
  2. Pausar cuando veas un golpe (SPACE)
  3. Retroceder al inicio del golpe (←)
  4. Presionar A para marcar inicio
  5. Avanzar al final del golpe (→)
  6. Presionar E para marcar fin
  7. Presionar tipo (J/C/H/U) y fighter (R/B)
  8. Presionar ENTER para confirmar
  9. Guardar frecuentemente (S)
"""

import cv2
import numpy as np
import json
import argparse
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict

# Para modo eval: cargar el sistema de detección
EVAL_AVAILABLE = False
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fighterid_vision_engine.detection.pose import PoseDetector
    from fighterid_vision_engine.detection.tracker import PersistentTracker
    from fighterid_vision_engine.pipeline.temporal_strike import TemporalStrikeAnalyzer
    EVAL_AVAILABLE = True
except ImportError:
    pass

# ── Colores (BGR) ────────────────────────────────────────────────────────
C_RED    = (40,  40, 220)
C_BLUE   = (220, 140, 30)
C_GREEN  = (60, 200, 60)
C_YELLOW = (0,  210, 230)
C_CYAN   = (200, 200, 30)
C_WHITE  = (255, 255, 255)
C_GRAY   = (120, 120, 120)
C_ORANGE = (0,  165, 255)

PUNCH_COLORS = {
    "jab":      C_CYAN,
    "cross":    C_RED,
    "hook":     C_ORANGE,
    "uppercut": C_YELLOW,
    "unknown":  C_GRAY,
}

FIGHTER_COLORS = {
    "red":  C_RED,
    "blue": C_BLUE,
    "any":  C_GREEN,
}

FONT = cv2.FONT_HERSHEY_SIMPLEX


# ── Estructura de anotación ─────────────────────────────────────────────

@dataclass
class Annotation:
    id:              int
    frame_start:     int
    frame_end:       Optional[int]  = None
    fighter:         str            = "any"   # "red" | "blue" | "any"
    wrist:           str            = "right" # "left" | "right"
    type:            str            = "punch" # "jab"|"cross"|"hook"|"uppercut"
    speed_estimate:  Optional[float]= None
    notes:           str            = ""
    confirmed:       bool           = False

    def is_complete(self) -> bool:
        return self.frame_end is not None and self.confirmed

    def duration_frames(self) -> int:
        if self.frame_end is None:
            return 0
        return self.frame_end - self.frame_start

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "frame_start":        self.frame_start,
            "frame_end":          self.frame_end,
            "fighter":            self.fighter,
            "wrist":              self.wrist,
            "type":               self.type,
            "speed_estimate_ms":  self.speed_estimate,
            "notes":              self.notes,
        }


# ── Anotador ────────────────────────────────────────────────────────────

class VideoAnnotator:

    def __init__(self, video_path: str, output_path: str,
                 eval_mode: bool = False):
        self.video_path  = video_path
        self.output_path = output_path
        self.eval_mode   = eval_mode and EVAL_AVAILABLE

        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se puede abrir: {video_path}")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps          = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_w      = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h      = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.frame_idx   = 0
        self.playing     = False
        self.frame_cache: dict[int, np.ndarray] = {}

        self.annotations: list[Annotation] = []
        self._next_id    = 1
        self._pending: Optional[Annotation] = None  # en construcción
        self._dirty  = False                         # cambios sin guardar

        # Modo eval
        if self.eval_mode:
            print("[EVAL] Cargando modelos de detección...")
            self.detector = PoseDetector()
            self.tracker  = PersistentTracker()
            self.analyzer = TemporalStrikeAnalyzer()
            self._auto_detections: dict[int, list] = defaultdict(list)
            self._eval_cache: dict[int, list] = {}
            print("[EVAL] Listo")

    def _read_frame(self, idx: int) -> Optional[np.ndarray]:
        """Lee un frame por índice (con caché simple)."""
        if idx in self.frame_cache:
            return self.frame_cache[idx].copy()
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self.cap.read()
        if ret:
            # Limitar caché a 60 frames
            if len(self.frame_cache) > 60:
                oldest = min(self.frame_cache.keys())
                del self.frame_cache[oldest]
            self.frame_cache[idx] = frame.copy()
            return frame
        return None

    def _eval_frame(self, frame: np.ndarray, idx: int) -> list[dict]:
        """Corre detección automática en un frame (modo eval)."""
        if not self.eval_mode:
            return []
        if idx in self._eval_cache:
            return self._eval_cache[idx]
        persons = self.detector.infer(frame)
        roles   = self.tracker.assign(persons)
        results = []
        for corner in ("red", "blue"):
            person   = roles.get(corner)
            opponent = roles.get("blue" if corner == "red" else "red")
            if person is None:
                continue
            hit, speed, conf, punch_type = self.analyzer.detect(
                corner, person, opponent)
            if hit:
                results.append({
                    "corner": corner, "speed": speed,
                    "conf": conf, "type": punch_type,
                })
        self._eval_cache[idx] = results
        return results

    def _annotations_at_frame(self, idx: int) -> list[Annotation]:
        """Retorna anotaciones activas en el frame dado."""
        return [a for a in self.annotations
                if a.frame_start <= idx
                and (a.frame_end is None or a.frame_end >= idx)]

    def _draw_hud(self, frame: np.ndarray, auto_dets: list) -> np.ndarray:
        """Dibuja el HUD completo sobre el frame."""
        disp = frame.copy()
        h, w = disp.shape[:2]

        # ── Barra de progreso temporal ──────────────────────────────────
        pct = self.frame_idx / max(self.total_frames - 1, 1)
        bar_y  = h - 24
        bar_h  = 6
        bar_w  = w - 20
        cv2.rectangle(disp, (10, bar_y), (10 + bar_w, bar_y + bar_h),
                      (40, 40, 40), -1)
        cv2.rectangle(disp, (10, bar_y), (10 + int(bar_w * pct), bar_y + bar_h),
                      C_CYAN, -1)

        # Marcas de anotaciones en la barra de tiempo
        for ann in self.annotations:
            ax = 10 + int(ann.frame_start / max(self.total_frames - 1, 1) * bar_w)
            col = FIGHTER_COLORS.get(ann.fighter, C_GREEN)
            cv2.line(disp, (ax, bar_y - 4), (ax, bar_y + bar_h + 2), col, 2)

        # Tiempo
        secs  = self.frame_idx / self.fps
        total = self.total_frames / self.fps
        cv2.putText(disp, f"{int(secs//60):02d}:{secs%60:05.2f} / "
                          f"{int(total//60):02d}:{total%60:05.2f}",
                    (10, h - 6), FONT, 0.45, C_WHITE, 1)
        cv2.putText(disp, f"Frame {self.frame_idx}/{self.total_frames-1}",
                    (w - 200, h - 6), FONT, 0.45, C_GRAY, 1)

        # ── Panel izquierdo: controles ───────────────────────────────────
        controls = [
            ("SPACE", "Play/Pausa"),
            ("← →",  "Frame prev/next"),
            ("A/E",  "Marcar inicio/fin"),
            ("J/C/H/U", "Tipo golpe"),
            ("R/B",  "Luchador rojo/azul"),
            ("ENTER", "Confirmar"),
            ("Del",  "Eliminar última"),
            ("S",    "Guardar"),
        ]
        for i, (key, desc) in enumerate(controls):
            cv2.putText(disp, f"{key}={desc}", (10, 25 + i * 17),
                        FONT, 0.38, C_GRAY, 1)

        # ── Estado actual ─────────────────────────────────────────────────
        cv2.putText(disp, f"{'▶ PLAY' if self.playing else '⏸ PAUSA'}",
                    (w - 150, 25), FONT, 0.7,
                    C_GREEN if self.playing else C_YELLOW, 2)

        # ── Anotaciones activas en frame actual ──────────────────────────
        active = self._annotations_at_frame(self.frame_idx)
        for i, ann in enumerate(active):
            col = FIGHTER_COLORS.get(ann.fighter, C_GREEN)
            pt  = ann.type.upper()
            dur = ann.duration_frames()
            cv2.putText(disp,
                f"#{ann.id} {pt} {ann.fighter.upper()} "
                f"({ann.frame_start}→{ann.frame_end or '?'} dur={dur}fr)",
                (10, h - 55 - i * 20), FONT, 0.5, col, 1)

        # ── Anotación en construcción ─────────────────────────────────────
        if self._pending:
            pen = self._pending
            col = FIGHTER_COLORS.get(pen.fighter, C_GREEN)
            info = (f"EN CONSTRUCCIÓN: inicio={pen.frame_start} "
                    f"fin={'?' if pen.frame_end is None else pen.frame_end} "
                    f"tipo={pen.type} fighter={pen.fighter} "
                    f"→ ENTER para confirmar")
            cv2.rectangle(disp, (0, h - 90), (w, h - 65), (30, 30, 70), -1)
            cv2.putText(disp, info, (10, h - 74), FONT, 0.45, col, 1)

        # ── Detecciones automáticas (eval mode) ──────────────────────────
        if auto_dets:
            for j, det in enumerate(auto_dets):
                col  = FIGHTER_COLORS.get(det["corner"], C_GREEN)
                text = (f"AUTO: {det['corner']} {det['type']} "
                        f"{det['speed']:.1f}m/s conf={det['conf']:.2f}")
                cv2.putText(disp, text, (w//2 - 150, 25 + j * 22),
                            FONT, 0.55, col, 2)

        # ── Contador de anotaciones ───────────────────────────────────────
        confirmed = sum(1 for a in self.annotations if a.is_complete())
        cv2.putText(disp,
            f"Anotaciones: {confirmed} confirmadas  "
            f"{'[sin guardar]' if self._dirty else '[guardado]'}",
            (w - 420, h - 35), FONT, 0.5,
            C_ORANGE if self._dirty else C_GRAY, 1)

        # ── Línea de escala temporal (marcas cada 5 frames) ──────────────
        for tick_f in range(0, self.total_frames, max(1, int(self.fps * 5))):
            tx = 10 + int(tick_f / max(self.total_frames - 1, 1) * bar_w)
            cv2.line(disp, (tx, bar_y - 2), (tx, bar_y - 6), C_GRAY, 1)

        return disp

    def _save(self) -> None:
        """Guarda las anotaciones en JSON."""
        data = {
            "video":        self.video_path,
            "fps":          self.fps,
            "total_frames": self.total_frames,
            "annotations":  [a.to_dict() for a in self.annotations
                             if a.is_complete()],
        }
        with open(self.output_path, "w") as f:
            json.dump(data, f, indent=2)
        self._dirty = False
        print(f"\n[GUARDADO] {self.output_path} "
              f"({sum(1 for a in self.annotations if a.is_complete())} anotaciones)")

    def _load_existing(self) -> None:
        """Carga anotaciones existentes si el archivo de salida ya existe."""
        if not Path(self.output_path).exists():
            return
        try:
            with open(self.output_path) as f:
                data = json.load(f)
            for raw in data.get("annotations", []):
                ann = Annotation(
                    id          = raw["id"],
                    frame_start = raw["frame_start"],
                    frame_end   = raw.get("frame_end"),
                    fighter     = raw.get("fighter", "any"),
                    wrist       = raw.get("wrist",   "right"),
                    type        = raw.get("type",    "punch"),
                    speed_estimate = raw.get("speed_estimate_ms"),
                    notes       = raw.get("notes", ""),
                    confirmed   = True,
                )
                self.annotations.append(ann)
                self._next_id = max(self._next_id, ann.id + 1)
            print(f"[CARGADO] {len(self.annotations)} anotaciones desde {self.output_path}")
        except Exception as e:
            print(f"[AVISO] No se pudo cargar {self.output_path}: {e}")

    def run(self) -> None:
        """Bucle principal del anotador."""
        self._load_existing()

        WIN = "FighterID — Anotador de Dataset"
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, min(1280, self.frame_w), min(800, self.frame_h + 100))

        print(f"\n[ANOTADOR] {Path(self.video_path).name}")
        print(f"  {self.total_frames} frames  |  {self.fps:.1f} FPS  |  "
              f"{self.frame_w}×{self.frame_h}")
        print(f"  Salida: {self.output_path}")
        print(f"  Controles: SPACE=play  ←/→=frame  A/E=inicio/fin  "
              f"J/C/H/U=tipo  R/B=fighter  ENTER=confirmar  S=guardar  Q=salir\n")

        last_save_t = time.time()
        play_fps    = self.fps
        last_frame_t = time.time()

        while True:
            # Avanzar frame si está reproduciendo
            if self.playing:
                now = time.time()
                if now - last_frame_t >= 1.0 / play_fps:
                    self.frame_idx = min(self.frame_idx + 1,
                                        self.total_frames - 1)
                    last_frame_t = now
                    if self.frame_idx >= self.total_frames - 1:
                        self.playing = False

            frame = self._read_frame(self.frame_idx)
            if frame is None:
                time.sleep(0.01)
                continue

            # Detecciones automáticas (eval mode)
            auto_dets = []
            if self.eval_mode:
                auto_dets = self._eval_frame(frame, self.frame_idx)

            disp = self._draw_hud(frame, auto_dets)
            cv2.imshow(WIN, disp)

            # Auto-guardado cada 2 minutos
            if self._dirty and time.time() - last_save_t > 120:
                self._save()
                last_save_t = time.time()

            delay = max(1, int(1000 / play_fps / 4) if self.playing else 30)
            key   = cv2.waitKey(delay) & 0xFF

            # ── Navegación ────────────────────────────────────────────────
            if key == ord(' '):
                self.playing = not self.playing

            elif key == 81 or key == 2:  # ← (Linux) o ← (macOS)
                self.playing  = False
                self.frame_idx = max(0, self.frame_idx - 1)

            elif key == 83 or key == 3:  # → (Linux) o → (macOS)
                self.playing  = False
                self.frame_idx = min(self.total_frames - 1, self.frame_idx + 1)

            elif key == ord(','):  # < = retroceder 30 frames
                self.playing  = False
                self.frame_idx = max(0, self.frame_idx - 30)

            elif key == ord('.'):  # > = avanzar 30 frames
                self.playing  = False
                self.frame_idx = min(self.total_frames - 1, self.frame_idx + 30)

            # ── Anotación ─────────────────────────────────────────────────
            elif key == ord('a'):  # Marcar inicio
                self._pending = Annotation(
                    id=self._next_id, frame_start=self.frame_idx)
                print(f"  ✓ Inicio marcado: frame {self.frame_idx}")

            elif key == ord('e'):  # Marcar fin
                if self._pending:
                    if self.frame_idx < self._pending.frame_start:
                        print("  ⚠ Fin debe ser ≥ inicio")
                    else:
                        self._pending.frame_end = self.frame_idx
                        print(f"  ✓ Fin marcado: frame {self.frame_idx} "
                              f"(duración: {self._pending.duration_frames()} frames)")
                else:
                    print("  ⚠ Primero marca el inicio con A")

            elif key == ord('j') and self._pending:
                self._pending.type  = "jab"
                self._pending.wrist = "left"
                print("  Tipo: JAB")

            elif key == ord('c') and self._pending:
                self._pending.type  = "cross"
                self._pending.wrist = "right"
                print("  Tipo: CROSS")

            elif key == ord('h') and self._pending:
                self._pending.type  = "hook"
                print("  Tipo: HOOK")

            elif key == ord('u') and self._pending:
                self._pending.type  = "uppercut"
                print("  Tipo: UPPERCUT")

            elif key == ord('r') and self._pending:
                self._pending.fighter = "red"
                print("  Fighter: ROJO")

            elif key == ord('b') and self._pending:
                self._pending.fighter = "blue"
                print("  Fighter: AZUL")

            elif key == 13:  # ENTER — confirmar anotación
                if self._pending:
                    if self._pending.frame_end is None:
                        print("  ⚠ Falta marcar el fin (E)")
                    else:
                        self._pending.confirmed = True
                        self.annotations.append(self._pending)
                        print(f"  ✓ Anotación #{self._pending.id} confirmada: "
                              f"{self._pending.type} {self._pending.fighter} "
                              f"[{self._pending.frame_start}→{self._pending.frame_end}]")
                        self._next_id += 1
                        self._pending = None
                        self._dirty   = True
                else:
                    print("  ⚠ Nada pendiente — usa A para comenzar")

            elif key in (8, 127):  # Backspace / Del — eliminar última
                if self._pending:
                    self._pending = None
                    print("  ↩ Anotación en construcción cancelada")
                elif self.annotations:
                    removed = self.annotations.pop()
                    print(f"  ↩ Anotación #{removed.id} eliminada")
                    self._dirty = True

            elif key == ord('s'):
                self._save()
                last_save_t = time.time()

            elif key == ord('n'):  # nueva sin pending
                if self._pending is None:
                    self._pending = Annotation(
                        id=self._next_id, frame_start=self.frame_idx)
                    print(f"  ✓ Nueva anotación iniciada en frame {self.frame_idx}")

            elif key in (ord('q'), 27):  # Q o ESC
                if self._dirty:
                    self._save()
                break

        cv2.destroyWindow(WIN)
        self.cap.release()
        self._print_summary()

    def _print_summary(self) -> None:
        """Imprime resumen final de anotaciones."""
        complete = [a for a in self.annotations if a.is_complete()]
        if not complete:
            print("\n[RESUMEN] Sin anotaciones completadas")
            return

        type_counts = defaultdict(int)
        fighter_counts = defaultdict(int)
        for a in complete:
            type_counts[a.type] += 1
            fighter_counts[a.fighter] += 1

        print(f"\n{'='*50}")
        print(f"  RESUMEN — {len(complete)} anotaciones")
        print(f"{'='*50}")
        print(f"  Archivo: {self.output_path}")
        print(f"\n  Tipos:")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {t:<12} {c:4d}")
        print(f"\n  Por luchador:")
        for f, c in sorted(fighter_counts.items(), key=lambda x: -x[1]):
            print(f"    {f:<12} {c:4d}")

        durs = [a.duration_frames() for a in complete if a.duration_frames() > 0]
        if durs:
            print(f"\n  Duración promedio: {np.mean(durs):.1f} frames "
                  f"({np.mean(durs)/self.fps*1000:.0f}ms)")
        print(f"{'='*50}\n")


# ── CLI ─────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Herramienta de anotación de golpes para FighterID")
    p.add_argument("--video",   required=True,
                   help="Video a anotar")
    p.add_argument("--output",  default=None,
                   help="Archivo JSON de salida (default: <video>_annotations.json)")
    p.add_argument("--eval",    action="store_true",
                   help="Mostrar detecciones automáticas del sistema (requiere modelos)")
    return p.parse_args()


def main():
    args = parse_args()

    video_path = args.video
    if not Path(video_path).exists():
        print(f"[ERROR] Video no encontrado: {video_path}")
        sys.exit(1)

    if args.output:
        out_path = args.output
    else:
        stem = Path(video_path).stem
        out_dir = Path("annotations")
        out_dir.mkdir(exist_ok=True)
        out_path = str(out_dir / f"{stem}_annotations.json")

    if args.eval and not EVAL_AVAILABLE:
        print("[AVISO] Módulos de detección no encontrados — modo eval desactivado")

    annotator = VideoAnnotator(video_path, out_path, eval_mode=args.eval)
    annotator.run()


if __name__ == "__main__":
    main()
