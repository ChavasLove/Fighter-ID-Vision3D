"""
FighterID Vision — vision_sync.py
Motor de escritura: crea peleas e inicia sesiones en el backend.

Arquitectura: SOLO ESCRITURA — este módulo escribe, la web lee.
No threading. No estado global. Funciones puras y síncronas.

Flujo típico:
    fight_id = crear_pelea(event_id, fighter_a_id, fighter_b_id)
    iniciar_sesion(device_id, fight_id)
    enviar_evento(device_id, fight_id, fighter_id, "jab", 0.92)
"""

from datetime import datetime, timezone

import requests

from fighterid_vision_engine.config import settings as _cfg


# ── Helper ─────────────────────────────────────────────────────────────────

def _headers() -> dict:
    """
    Cabeceras estándar para Supabase PostgREST / Edge Functions.
    Idénticas a las usadas en fighterid_supabase_bridge.py y engine.py.
    """
    return {
        "Authorization": f"Bearer {_cfg.FIGHTERID_API_KEY}",
        "Content-Type":  "application/json",
        "apikey":         _cfg.FIGHTERID_API_KEY,
    }


# ── Funciones públicas ─────────────────────────────────────────────────────

def crear_pelea(event_id, fighter_a_id, fighter_b_id):
    """
    Crea una nueva fila en public.fights vía PostgREST REST API.

    Args:
        event_id     : UUID del evento de boxeo (puede ser None)
        fighter_a_id : UUID del peleador A (debe existir en fighter_profiles)
        fighter_b_id : UUID del peleador B (debe existir en fighter_profiles)

    Returns:
        fight_id (str UUID) si la inserción fue exitosa, None en caso de error.
    """
    if not _cfg.API_ENABLED:
        print("[vision_sync] API_ENABLED=false — crear_pelea omitida")
        return None

    url = f"{_cfg.SUPABASE_URL}/rest/v1/fights"

    body = {
        "fighter_a_id": fighter_a_id,
        "fighter_b_id": fighter_b_id,
    }
    if event_id is not None:
        body["event_id"] = event_id

    try:
        r = requests.post(
            url,
            json=body,
            headers={**_headers(), "Prefer": "return=representation"},
            timeout=5,
        )
        if r.status_code in (200, 201):
            data = r.json()
            # PostgREST devuelve lista cuando Prefer: return=representation
            fight = data[0] if isinstance(data, list) else data
            fight_id = fight.get("id")
            print(f"[vision_sync] ✅ pelea creada → fight_id={fight_id}")
            return fight_id
        print(f"[vision_sync] ❌ crear_pelea HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"[vision_sync] ❌ crear_pelea error: {e}")
    return None


def iniciar_sesion(device_id, fight_id):
    """
    Inicia una sesión de inferencia IA en el backend.

    POST {FIGHTERID_API_URL}/start

    Args:
        device_id : ID del dispositivo (normalmente _cfg.DEVICE_ID)
        fight_id  : UUID de la pelea activa (de crear_pelea o de la web)

    Returns:
        dict con la respuesta del backend, o None en caso de error.
    """
    if not _cfg.API_ENABLED:
        print("[vision_sync] API_ENABLED=false — iniciar_sesion omitida")
        return None

    url = f"{_cfg.FIGHTERID_API_URL}/start"

    body = {
        "device_id": device_id,
        "fight_id":  fight_id,
    }

    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=5)
        if r.status_code < 300:
            data = r.json()
            print(f"[vision_sync] 🟢 sesión iniciada → {data}")
            return data
        print(f"[vision_sync] ❌ iniciar_sesion HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"[vision_sync] ❌ iniciar_sesion error: {e}")
    return None


def enviar_evento(device_id, fight_id, fighter_id, tipo, confidence):
    """
    Envía un evento de golpe detectado al backend en tiempo real.

    POST {FIGHTERID_API_URL}/event

    Args:
        device_id  : ID del dispositivo
        fight_id   : UUID de la pelea activa
        fighter_id : UUID del peleador que ejecutó el golpe (fighter_profiles)
        tipo       : tipo de golpe ("jab", "cross", "hook", "uppercut", etc.)
        confidence : confianza de detección (float 0.0–1.0)

    Returns:
        dict con la respuesta del backend, o None en caso de error.
    """
    if not _cfg.API_ENABLED:
        # Sin print — esta función se llama en bucle ajustado de detección.
        return None

    url = f"{_cfg.FIGHTERID_API_URL}/event"

    body = {
        "device_id":  device_id,
        "fight_id":   fight_id,
        "fighter_id": fighter_id,
        "type":       tipo,
        "confidence": round(float(confidence), 3),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }

    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=5)
        if r.status_code < 300:
            return r.json()
        print(f"[vision_sync] ❌ enviar_evento HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"[vision_sync] ❌ enviar_evento error: {e}")
    return None
