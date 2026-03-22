"""
FighterID Vision Motor — entry point headless
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Uso:
  python main.py --fight-id <uuid-de-la-web>
  python main.py --fight-id <uuid> --cam-a 0 --cam-b 1 --cam-c 2
  FIGHT_ID=<uuid> python main.py

Contrato:
  - fight_id viene SIEMPRE de la web (fighter-id.org) — el motor NUNCA lo inventa
  - Las credenciales se leen de .env (ver .env.example)
  - Para la interfaz gráfica: usa main_gui.py

Checklist de arranque:
  [GPU]      torch-directml → AMD GPU  (o CUDA/CPU)
  [CAM MAP]  {'A': 0, 'B': 1, 'C': 2}
  [ONNX]     Cargado — providers=[DmlExecutionProvider]
  [SYNC OK]  fight=<uuid>  session=<uuid>
  [FIGHTERS] red=<uuid>  blue=<uuid>
  [MOTOR]    Bucle de detección iniciado — Ctrl+C para detener
"""

import argparse
import os
import sys

from fighterid_vision_engine.pipeline.engine import VisionMotorV1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FighterID Vision Motor — headless, sin GUI"
    )
    parser.add_argument(
        "--fight-id",
        default=None,
        help=(
            "Fight ID creado por la web (fighter-id.org). "
            "También puede pasarse via env var FIGHT_ID."
        ),
    )
    parser.add_argument(
        "--cam-a", type=int, default=0,
        help="Índice OpenCV cámara A — lateral principal (default: 0)",
    )
    parser.add_argument(
        "--cam-b", type=int, default=1,
        help="Índice OpenCV cámara B — lateral profundidad/estéreo (default: 1)",
    )
    parser.add_argument(
        "--cam-c", type=int, default=2,
        help="Índice OpenCV cámara C — cenital overhead (default: 2)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        default=False,
        help="Mostrar ventana de video en tiempo real con detecciones superpuestas. ESC para cerrar.",
    )
    args = parser.parse_args()

    fight_id = args.fight_id or os.environ.get("FIGHT_ID")

    if not fight_id:
        print("[MOTOR] Buscando sesión activa en Supabase...")
        from fighterid_vision_engine.pipeline.engine import discover_fight_id
        fight_id = discover_fight_id()

    if not fight_id:
        print("[ERROR] No hay sesión activa en Supabase.")
        print("        Crea una sesión desde la web (fighter-id.org) primero.")
        print()
        print("  Override manual:  python main.py --fight-id <uuid>")
        sys.exit(1)

    if args.fight_id:
        print(f"[SOURCE] fight_id desde CLI: {fight_id}")
    elif os.environ.get("FIGHT_ID"):
        print(f"[SOURCE] fight_id desde ENV: {fight_id}")
    else:
        print(f"[SOURCE] fight_id desde AUTO-DISCOVERY: {fight_id}")

    motor = VisionMotorV1(
        fight_id=fight_id,
        cam_a=args.cam_a,
        cam_b=args.cam_b,
        cam_c=args.cam_c,
        show=args.show,
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
