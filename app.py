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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["engine", "ui"], required=True)
    parser.add_argument("--fight-id", type=str)
    parser.add_argument("--show", action="store_true")

    args = parser.parse_args()

    if args.mode == "engine":
        run_engine(args.fight_id, args.show)

    elif args.mode == "ui":
        run_ui()


if __name__ == "__main__":
    main()