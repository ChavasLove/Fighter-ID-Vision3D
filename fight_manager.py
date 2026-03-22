"""
FighterID Vision — fight_manager.py
Núcleo de control total del motor de visión.

🥊 FLUJO COMPLETO:
    fighter_a = seleccionar_peleador("Peleador A")
    fighter_b = seleccionar_peleador("Peleador B")
    fight_id  = crear_pelea(None, fighter_a["id"], fighter_b["id"])
    iniciar_sesion(DEVICE_ID, fight_id)
    # Durante detección:
    enviar_evento(DEVICE_ID, fight_id, fighter_a["id"], "jab", 0.92)

Arquitectura: MOTOR escribe → WEB lee (sin conflictos).
Auto-contenido: usa load_dotenv() directamente, sin dependencia de
fighterid_vision_engine.config.
"""

import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ───────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

# Acepta SUPABASE_KEY (nombre corto) o SUPABASE_ANON_KEY (nombre completo).
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("FIGHTERID_API_KEY", "")
)

DEVICE_ID = os.getenv("DEVICE_ID", "vision-pc-1")

if not SUPABASE_URL:
    print("[fight_manager] ⚠  SUPABASE_URL no definida — crea .env desde .env.example")
if not SUPABASE_KEY:
    print("[fight_manager] ⚠  SUPABASE_KEY / SUPABASE_ANON_KEY no definida")


# ── Helper ──────────────────────────────────────────────────────────────────
def _headers() -> dict:
    return {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey":         SUPABASE_KEY,
    }


# ========================= #
# 🔍 BUSCAR PELEADOR        #
# ========================= #
def buscar_peleador(nombre: str) -> list:
    """
    Busca peleadores por nombre en fighter_profiles (búsqueda parcial).

    Args:
        nombre : texto a buscar (se aplica ilike en el campo 'name')

    Returns:
        Lista de dicts con keys: id, nombre, nickname, gym, weight_class
    """
    url = (
        f"{SUPABASE_URL}/rest/v1/fighter_profiles"
        f"?name=ilike.*{requests.utils.quote(nombre)}*"
        f"&select=id,name,nickname,weight_class,gym"
    )

    try:
        r = requests.get(url, headers=_headers(), timeout=5)
        if r.status_code == 200:
            return [
                {
                    "id":           f.get("id"),
                    "nombre":       f.get("name", ""),
                    "nickname":     f.get("nickname", ""),
                    "gym":          f.get("gym", ""),
                    "weight_class": f.get("weight_class", ""),
                }
                for f in r.json()
            ]
        print(f"[fight_manager] ❌ buscar_peleador HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[fight_manager] ❌ buscar_peleador error: {e}")
    return []


# ========================= #
# 🎯 SELECCIONAR PELEADOR   #
# ========================= #
def seleccionar_peleador(label: str = "Peleador") -> dict:
    """
    Flujo interactivo CLI: busca y selecciona un peleador por nombre.

    Args:
        label : etiqueta mostrada al usuario ("Peleador A", "Peleador B", etc.)

    Returns:
        dict del peleador seleccionado (con key 'id').
    """
    while True:
        nombre = input(f"\n🔍 Buscar {label}: ").strip()
        if not nombre:
            continue

        resultados = buscar_peleador(nombre)

        if not resultados:
            print("   Sin resultados — intenta de nuevo.")
            continue

        print(f"\n   Resultados para '{nombre}':")
        for i, f in enumerate(resultados, 1):
            nick  = f"  "{f['nickname']}"" if f["nickname"] else ""
            gym   = f"  {f['gym']}" if f["gym"] else ""
            clase = f"  [{f['weight_class']}]" if f["weight_class"] else ""
            print(f"   [{i}] {f['nombre']}{nick}{gym}{clase}")

        try:
            idx = int(input(f"\n   Selecciona [{label}] número: ").strip()) - 1
            if 0 <= idx < len(resultados):
                elegido = resultados[idx]
                print(f"   ✅ {label}: {elegido['nombre']}  (id={elegido['id']})")
                return elegido
        except (ValueError, IndexError):
            pass

        print("   Selección inválida — intenta de nuevo.")


# ========================= #
# 🥊 CREAR PELEA            #
# ========================= #
def crear_pelea(event_id, fighter_a_id: str, fighter_b_id: str):
    """
    Crea una nueva fila en public.fights vía PostgREST.

    Args:
        event_id     : UUID del evento (puede ser None)
        fighter_a_id : UUID del peleador A
        fighter_b_id : UUID del peleador B

    Returns:
        fight_id (str UUID) o None en caso de error.
    """
    url = f"{SUPABASE_URL}/rest/v1/fights"

    payload = {
        "fighter_a_id": fighter_a_id,
        "fighter_b_id": fighter_b_id,
        "status":       "in_progress",
        "fight_number": 1,
    }
    if event_id is not None:
        payload["event_id"] = event_id

    try:
        r = requests.post(
            url,
            json=payload,
            headers={**_headers(), "Prefer": "return=representation"},
            timeout=5,
        )
        if r.status_code in (200, 201):
            data  = r.json()
            fight = data[0] if isinstance(data, list) else data
            fight_id = fight.get("id")
            print(f"[fight_manager] ✅ Fight creada: {fight_id}")
            return fight_id
        print(f"[fight_manager] ❌ Error creando pelea: {r.text[:300]}")
    except Exception as e:
        print(f"[fight_manager] ❌ crear_pelea error: {e}")
    return None


# ========================= #
# 🟢 INICIAR SESIÓN IA      #
# ========================= #
def iniciar_sesion(device_id: str, fight_id: str):
    """
    Inicia la sesión de inferencia IA en el backend.

    POST {SUPABASE_URL}/functions/v1/ai-strike-ingest/start
    """
    url = f"{SUPABASE_URL}/functions/v1/ai-strike-ingest/start"

    payload = {
        "device_id": device_id,
        "fight_id":  fight_id,
    }

    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=5)
        print("START:", r.status_code, r.text[:200])
        return r
    except Exception as e:
        print(f"[fight_manager] ❌ iniciar_sesion error: {e}")
    return None


# ========================= #
# 🔥 ENVIAR EVENTO          #
# ========================= #
def enviar_evento(device_id: str, fight_id: str, fighter_id: str,
                  tipo: str, confidence: float):
    """
    Envía un evento de golpe detectado al backend en tiempo real.

    POST {SUPABASE_URL}/functions/v1/ai-strike-ingest/event
    """
    url = f"{SUPABASE_URL}/functions/v1/ai-strike-ingest/event"

    payload = {
        "device_id":  device_id,
        "fight_id":   fight_id,
        "fighter_id": fighter_id,
        "type":       tipo,
        "confidence": confidence,
        "timestamp":  datetime.utcnow().isoformat(),
    }

    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=5)
        print("EVENT:", r.status_code, r.text[:200])
        return r
    except Exception as e:
        print(f"[fight_manager] ❌ enviar_evento error: {e}")
    return None


# ========================= #
# 🚀 EJEMPLO DE USO REAL    #
# ========================= #
if __name__ == "__main__":
    print("=" * 50)
    print("  FighterID — Panel de Control del Motor")
    print("=" * 50)

    fighter_a = seleccionar_peleador("Peleador A")
    fighter_b = seleccionar_peleador("Peleador B")

    fight_id = crear_pelea(
        event_id=None,
        fighter_a_id=fighter_a["id"],
        fighter_b_id=fighter_b["id"],
    )

    if not fight_id:
        print("\n❌ No se pudo crear la pelea. Verifica .env y la tabla fights.")
        raise SystemExit(1)

    iniciar_sesion(DEVICE_ID, fight_id)

    print("\n🎯 Simulación de detección (jab con 0.92 de confianza)...")
    enviar_evento(DEVICE_ID, fight_id, fighter_a["id"], "jab", 0.92)

    print(f"\n✅ fight_id listo para el motor: {fight_id}")
    print("   Úsalo con:  python app.py --mode engine --fight-id", fight_id)
