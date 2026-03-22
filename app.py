import argparse
import os
import sys


def run_engine(fight_id=None, show=False):
    cmd = "python main.py"

    if fight_id:
        cmd += f" --fight-id {fight_id}"

    if show:
        cmd += " --show"

    print(f"[APP] Ejecutando motor: {cmd}")
    os.system(cmd)


def run_ui():
    print("[APP] Ejecutando dashboard (3 cámaras)...")
    os.system("python three_camera_ui.py")


def run_fight(show=False):
    """
    Flujo completo de control:
      1. Selecciona Peleador A y Peleador B interactivamente
      2. Crea la pelea en Supabase (tabla fights)
      3. Inicia sesión IA (ai-strike-ingest/start)
      4. Lanza el motor de visión con el fight_id resultante

    Uso: python app.py --mode fight [--show]
    """
    import fight_manager

    print("\n🎛️  PANEL DE CONTROL — FighterID Vision")
    print("─" * 42)

    # ── 1. Buscar y seleccionar peleadores ───────────────────────────
    fighter_a = fight_manager.seleccionar_peleador("Peleador A")
    fighter_b = fight_manager.seleccionar_peleador("Peleador B")

    print(f"\n🥊 {fighter_a['nombre']}  vs  {fighter_b['nombre']}")

    # ── 2. Crear pelea ───────────────────────────────────────────────
    fight_id = fight_manager.crear_pelea(
        event_id=None,
        fighter_a_id=fighter_a["id"],
        fighter_b_id=fighter_b["id"],
    )

    if not fight_id:
        print("\n❌ No se pudo crear la pelea. Verifica .env y la tabla fights en Supabase.")
        sys.exit(1)

    # ── 3. Iniciar sesión IA ─────────────────────────────────────────
    device_id = fight_manager.DEVICE_ID
    fight_manager.iniciar_sesion(device_id, fight_id)

    print(f"\n🚀 Iniciando motor con fight_id={fight_id}")
    print("─" * 42)

    # ── 4. Lanzar motor de visión ────────────────────────────────────
    run_engine(fight_id, show)


def main():
    parser = argparse.ArgumentParser(description="FighterID Vision — Launcher")
    parser.add_argument("--mode", choices=["engine", "ui", "fight"], required=True,
                        help="engine: motor headless | ui: dashboard GUI | fight: control total")
    parser.add_argument("--fight-id", type=str, help="UUID de la pelea (solo para --mode engine)")
    parser.add_argument("--show", action="store_true", help="Mostrar ventana de video")

    args = parser.parse_args()

    if args.mode == "engine":
        run_engine(args.fight_id, args.show)

    elif args.mode == "ui":
        run_ui()

    elif args.mode == "fight":
        run_fight(args.show)


if __name__ == "__main__":
    main()