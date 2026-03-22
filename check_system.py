"""
FighterID Vision3D — Diagnóstico del sistema
Corre este script para verificar ONNX providers, modelo y conexión Supabase.

Uso:
    python check_system.py
"""

import os
import sys

# ── 1. ONNX providers ──────────────────────────────────────────────────────
print("=" * 60)
print("1. ONNX Runtime providers disponibles")
print("=" * 60)
try:
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print(f"   Providers: {providers}")
    if "DmlExecutionProvider" in providers:
        print("   ✓ DmlExecutionProvider disponible — AMD GPU activa")
    elif "CUDAExecutionProvider" in providers:
        print("   ✓ CUDAExecutionProvider disponible — NVIDIA GPU activa")
    else:
        print("   ⚠ Solo CPUExecutionProvider — sin aceleración GPU")
        print("     Solución: actualizar drivers GPU o reinstalar onnxruntime-directml")
except ImportError:
    print("   ✗ onnxruntime no instalado — pip install onnxruntime-directml")
    sys.exit(1)

# ── 2. Test ONNX con modelo ────────────────────────────────────────────────
print()
print("=" * 60)
print("2. Test ONNX con yolov8n-pose.onnx")
print("=" * 60)
import numpy as np

_PKG_DIR   = os.path.join(os.path.dirname(__file__), "fighterid_vision_engine")
_MODEL_DIR = os.path.join(_PKG_DIR, "models")
onnx_path  = os.path.join(_MODEL_DIR, "yolov8n-pose.onnx")

if not os.path.exists(onnx_path):
    onnx_path = "yolov8n-pose.onnx"  # fallback al cwd

if os.path.exists(onnx_path):
    try:
        sess    = ort.InferenceSession(onnx_path, providers=providers)
        inp     = sess.get_inputs()[0]
        dummy   = np.zeros((1, 3, 640, 640), dtype=np.float32)
        out     = sess.run(None, {inp.name: dummy})
        active  = sess.get_providers()[0]
        print(f"   ✓ ONNX OK — provider activo: {active}")
        print(f"     Input:  {inp.name} {inp.shape}")
        print(f"     Output: shape={out[0].shape}")
        if active == "DmlExecutionProvider":
            print("   ✓ GPU acelerada confirmada")
        else:
            print("   ⚠ Usando CPU — GPU no activada")
    except Exception as e:
        print(f"   ✗ Error cargando ONNX: {e}")
else:
    print(f"   ⚠ Modelo no encontrado en {onnx_path}")
    print("     El motor lo exportará automáticamente al arrancar.")

# ── 3. Supabase conexión ───────────────────────────────────────────────────
print()
print("=" * 60)
print("3. Conexión Supabase")
print("=" * 60)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

supabase_url = os.getenv(
    "SUPABASE_URL",
    "https://eeshomcqztvjkvycdfwi.supabase.co",
)
print(f"   URL: {supabase_url}")

try:
    import requests
    r = requests.get(
        f"{supabase_url}/rest/v1/",
        timeout=5,
    )
    print(f"   HTTP status: {r.status_code}")
    if r.status_code < 500:
        print("   ✓ Supabase alcanzable")
    else:
        print("   ✗ Error de servidor Supabase")
except Exception as e:
    print(f"   ✗ No se puede conectar a Supabase: {e}")

# ── 4. Resumen ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("Resumen")
print("=" * 60)
print(f"   ONNX providers: {providers}")
print(f"   GPU activa:     {'DmlExecutionProvider' in providers or 'CUDAExecutionProvider' in providers}")
print(f"   Modelo ONNX:    {'encontrado' if os.path.exists(onnx_path) else 'no encontrado (se exportará al arrancar)'}")
print()
print("Para forzar CPU (debug): FORCE_CPU=true en .env")
print("Para ajustar detección:  POSE_CONF_THR=0.20 en .env (bajar si no detecta)")
