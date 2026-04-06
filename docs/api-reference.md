# FighterID — 3D Vision Engine API Reference

**Version:** 3.4
**Date:** 2026-04-06
**Supabase Project:** `eeshomcqztvjkvycdfwi`

---

## 1. Base URL

```
https://eeshomcqztvjkvycdfwi.supabase.co/functions/v1/ai-strike-ingest
```

Required headers on **all** requests:

```http
Authorization: Bearer <SUPABASE_ANON_KEY>
Content-Type: application/json
apikey: <SUPABASE_ANON_KEY>
```

---

## 2. Available Endpoints

| Method | Path         | Description                                   |
|--------|--------------|-----------------------------------------------|
| POST   | `/start`     | Start session — returns fighters with avatar_url |
| POST   | `/heartbeat` | Engine heartbeat (upsert telemetry)           |
| POST   | `/event`     | Register a strike (strike_attempted / strike_connected) |
| POST   | `/stop`      | Stop inference session                        |
| POST   | `/end`       | End fight and calculate stats                 |
| POST   | `/log`       | Register diagnostic log                       |
| GET    | `/health`    | Health check                                  |
| GET    | `/metrics`   | Active sessions                               |

---

## 3. Typical Flow

```
1. POST /start      { fight_id, device_id }
   → Returns session_id + fighters (with avatar_url)

2. POST /heartbeat  { fight_id, device_id, fps, persons }
   → Every 3–5 seconds

3. POST /event      { fight_id, session_id, fighter, type, confidence, round, strike_type }
   → For each detected strike

4. POST /stop       { session_id }
   → When the engine stops

5. POST /end        { fight_id }
   → Closes the fight and calculates statistics
```

---

## 4. Response from `/start` (fighter data)

```json
{
  "session_id": "uuid",
  "fight_id": "uuid",
  "fighters": {
    "red": {
      "id": "uuid",
      "name": "Juan Pérez",
      "nickname": "El Tigre",
      "record": "5-2-0",
      "weight_class": "welterweight",
      "avatar_url": "https://eeshomcqztvjkvycdfwi.supabase.co/storage/v1/object/public/fighter-avatars/uuid/photo.jpg"
    },
    "blue": {
      "id": "uuid",
      "name": "Carlos López",
      "nickname": "La Sombra",
      "record": "3-1-1",
      "weight_class": "welterweight",
      "avatar_url": "https://eeshomcqztvjkvycdfwi.supabase.co/storage/v1/object/public/fighter-avatars/uuid/photo.jpg"
    }
  },
  "event": {
    "name": "Batalla en el Ring 5",
    "date": "2026-04-10T20:00:00Z",
    "venue": "Arena CDMX"
  }
}
```

---

## 5. Storage — Fighter Photo Buckets

All photo buckets are **public** (no auth required for reads):

| Bucket                    | Contents                        | URL Pattern                                                              |
|---------------------------|---------------------------------|--------------------------------------------------------------------------|
| `fighter-avatars`         | Profile photos (used in avatar_url) | `/storage/v1/object/public/fighter-avatars/{path}`                   |
| `fighter-photos`          | Additional fighter photos       | `/storage/v1/object/public/fighter-photos/{path}`                        |
| `external-fighter-images` | External fighter photos         | `/storage/v1/object/public/external-fighter-images/{path}`               |
| `event-fighter-images`    | Fighter photos at events        | `/storage/v1/object/public/event-fighter-images/{path}`                  |

The engine only needs to use `avatar_url` from the `/start` response. It does not need to list or navigate buckets directly.

**Storage base URL:**
```
https://eeshomcqztvjkvycdfwi.supabase.co/storage/v1/object/public/
```

---

## 6. Tables Used by the Engine (via Edge Function)

The engine does **not** access these tables directly — the Edge Function handles them internally:

| Table / View                  | Access       | Description                                           |
|-------------------------------|--------------|-------------------------------------------------------|
| `vision_fight_context` (VIEW) | READ         | Enriched fight data (names, records, avatars, event)  |
| `fights`                      | READ/WRITE   | Fight state (`scheduled` → `active` → `finished`)     |
| `ai_inference_sessions`       | WRITE        | Engine inference sessions                             |
| `ai_strike_events`            | WRITE        | Detected strikes (timestamp, fighter, type, confidence)|
| `ai_fight_results`            | WRITE        | Statistics calculated at fight end                    |
| `fight_telemetry_sessions`    | WRITE        | Heartbeats and connection state                       |
| `ai_inference_logs`           | WRITE        | Diagnostic logs                                       |

### `vision_fight_context` View — Available Columns

| Column             | Type        | Description                                |
|--------------------|-------------|--------------------------------------------|
| `fight_id`         | uuid        | Fight ID                                   |
| `event_id`         | uuid        | Event ID                                   |
| `fight_number`     | integer     | Fight number on the card                   |
| `status`           | text        | State: `scheduled`, `ready`, `active`, `finished` |
| `weight_class`     | text        | Fight weight class                         |
| `fighter_a_id`     | uuid        | Red fighter ID                             |
| `fighter_a_name`   | text        | Full name                                  |
| `fighter_a_nickname` | text      | Nickname                                   |
| `fighter_a_weight` | text        | Fighter profile weight class               |
| `fighter_a_avatar` | text        | Public profile photo URL                   |
| `fighter_a_wins`   | integer     | Wins                                       |
| `fighter_a_losses` | integer     | Losses                                     |
| `fighter_a_draws`  | integer     | Draws                                      |
| `fighter_b_id`     | uuid        | Blue fighter ID                            |
| `fighter_b_name`   | text        | Full name                                  |
| `fighter_b_nickname` | text      | Nickname                                   |
| `fighter_b_weight` | text        | Fighter profile weight class               |
| `fighter_b_avatar` | text        | Public profile photo URL                   |
| `fighter_b_wins`   | integer     | Wins                                       |
| `fighter_b_losses` | integer     | Losses                                     |
| `fighter_b_draws`  | integer     | Draws                                      |
| `event_name`       | text        | Event name                                 |
| `event_date`       | timestamptz | Event date                                 |
| `event_venue`      | text        | Event venue                                |

---

## 7. `/start` Endpoint Validations

The endpoint rejects the session if:

- `fight_id` does not exist → `400`
- The fight does not have both fighters assigned → `422` with detail of which is missing
- Status is not `scheduled`, `ready`, or `active` → `409`
- The fight has already been finalized → `409`

---

## 8. `/event` Schema (register a strike)

```json
{
  "fight_id":    "uuid (required)",
  "session_id":  "uuid (optional)",
  "fighter":     "A | B",
  "type":        "strike_attempted | strike_connected",
  "strike_type": "jab | cross | hook | uppercut | body | kick | knee | elbow | other",
  "confidence":  0.0,
  "round":       1,
  "timestamp":   1712345678000
}
```

**Field details:**

| Field        | Type    | Required | Description                                      |
|--------------|---------|----------|--------------------------------------------------|
| `fight_id`   | uuid    | Yes      | Fight identifier                                 |
| `session_id` | uuid    | No       | Inference session ID from `/start`               |
| `fighter`    | string  | Yes      | `"A"` (red) or `"B"` (blue)                     |
| `type`       | string  | Yes      | `"strike_attempted"` or `"strike_connected"`     |
| `strike_type`| string  | Yes      | Strike classification (see values above)         |
| `confidence` | float   | Yes      | Detection confidence score (0.0–1.0)             |
| `round`      | integer | Yes      | Round number                                     |
| `timestamp`  | integer | No       | Unix timestamp in milliseconds                   |

---

## 9. Quick Example (Python)

```python
import requests

BASE = "https://eeshomcqztvjkvycdfwi.supabase.co/functions/v1/ai-strike-ingest"
HEADERS = {
    "Authorization": "Bearer <ANON_KEY>",
    "apikey": "<ANON_KEY>",
    "Content-Type": "application/json"
}

# 1. Start session
r = requests.post(f"{BASE}/start", json={
    "fight_id": "<FIGHT_UUID>",
    "device_id": "vision_engine_01"
}, headers=HEADERS)

data = r.json()
session_id = data["session_id"]
red_avatar  = data["fighters"]["red"]["avatar_url"]   # Public photo URL
blue_avatar = data["fighters"]["blue"]["avatar_url"]

print(f"Red:  {data['fighters']['red']['name']}  → {red_avatar}")
print(f"Blue: {data['fighters']['blue']['name']} → {blue_avatar}")

# 2. Register a strike
requests.post(f"{BASE}/event", json={
    "fight_id":    "<FIGHT_UUID>",
    "session_id":  session_id,
    "fighter":     "A",
    "type":        "strike_connected",
    "strike_type": "jab",
    "confidence":  0.92,
    "round":       1,
    "timestamp":   1712345678000
}, headers=HEADERS)

# 3. Heartbeat
requests.post(f"{BASE}/heartbeat", json={
    "fight_id":  "<FIGHT_UUID>",
    "device_id": "vision_engine_01",
    "fps":       30,
    "persons":   2
}, headers=HEADERS)

# 4. End fight
requests.post(f"{BASE}/end", json={
    "fight_id": "<FIGHT_UUID>"
}, headers=HEADERS)
```

---

## 10. Sync Notes

- **Photos sync on `/start`** — if `avatar_url` is `null`, the fighter profile has no photo uploaded on the platform.
- **Names are normalized** — the view uses `COALESCE(NULLIF(name,''), CONCAT_WS(' ', first_name, last_name))`.
- **Records reflect current state** — `wins`/`losses`/`draws` come from `fighter_profiles` at the time of the call.
- **`fighter-avatars` bucket is public** — URLs require no authentication to download.
