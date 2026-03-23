/**
 * FighterID — Edge Function: ai-strike-ingest
 *
 * Contrato del motor de visión IA (ÚNICO flujo permitido):
 *   START → eventos → STOP
 *
 * Rutas:
 *   POST /ai-strike-ingest/start   → Inicia sesión de inferencia
 *   POST /ai-strike-ingest/event   → Inserta golpe detectado
 *   POST /ai-strike-ingest/stop    → Cierra sesión
 *
 * Reglas del motor de visión:
 *   ✔  Detectar golpes
 *   ✔  Clasificar esquina (red / blue)
 *   ✔  Enviar eventos
 *   ✗  NO crea peleas
 *   ✗  NO modifica estados de negocio
 *   ✗  NO inventa fighter_id (lo resuelve esta función desde corner)
 *   ✗  NO maneja lógica de scoring
 *
 * Deploy:
 *   supabase functions deploy ai-strike-ingest
 */

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

serve(async (req: Request) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  // Sólo POST
  if (req.method !== "POST") {
    return json({ error: "Method not allowed. Use POST." }, 405);
  }

  // Cliente con service role key — necesario para bypass RLS en escrituras
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } }
  );

  // Despachar por sufijo de ruta: /start | /event | /stop
  const suffix = new URL(req.url).pathname.split("/").pop();

  // ── POST /start ───────────────────────────────────────────────────────────
  if (suffix === "start") {
    let body: { fight_id?: string; device_id?: string; model_version?: string };
    try {
      body = await req.json();
    } catch {
      return json({ error: "Invalid JSON body" }, 400);
    }

    const { fight_id, device_id, model_version } = body;

    if (!fight_id || !device_id) {
      return json({ error: "fight_id and device_id are required" }, 400);
    }

    // 1. Validar que la pelea existe y obtener IDs + nombres de peleadores
    const { data: fightCtx, error: fightErr } = await supabase
      .from("fight_full_context")
      .select(
        "fight_id, fighter_red_id, fighter_red_name, fighter_blue_id, fighter_blue_name"
      )
      .eq("fight_id", fight_id)
      .single();

    if (fightErr || !fightCtx) {
      return json(
        { error: "Fight not found", detail: fightErr?.message },
        404
      );
    }

    // 2. Upsert fight_telemetry_sessions (idempotente — safe re-start)
    const { data: session, error: sessionErr } = await supabase
      .from("fight_telemetry_sessions")
      .upsert(
        {
          fight_id,
          status:           "active",
          vision_connected: true,
          fighter_red_id:   fightCtx.fighter_red_id,
          fighter_blue_id:  fightCtx.fighter_blue_id,
          model_version:    model_version ?? "v1.0",
          last_heartbeat:   new Date().toISOString(),
        },
        { onConflict: "fight_id", ignoreDuplicates: false }
      )
      .select("id, fight_id, fighter_red_id, fighter_blue_id")
      .single();

    if (sessionErr || !session) {
      return json(
        { error: "Failed to create session", detail: sessionErr?.message },
        500
      );
    }

    return json({
      session_id: session.id,
      fight_id:   session.fight_id,
      fighters: {
        red:  { id: session.fighter_red_id,  name: fightCtx.fighter_red_name  },
        blue: { id: session.fighter_blue_id, name: fightCtx.fighter_blue_name },
      },
    });
  }

  // ── POST /event ───────────────────────────────────────────────────────────
  if (suffix === "event") {
    let body: {
      fight_id?: string;
      corner?: string;
      confidence?: number;
      strike_type?: string;
    };
    try {
      body = await req.json();
    } catch {
      return json({ error: "Invalid JSON body" }, 400);
    }

    const { fight_id, corner, confidence, strike_type } = body;

    if (!fight_id || !corner || confidence == null || !strike_type) {
      return json(
        { error: "fight_id, corner, confidence and strike_type are required" },
        400
      );
    }
    if (corner !== "red" && corner !== "blue") {
      return json({ error: "corner must be 'red' or 'blue'" }, 400);
    }

    // 1. Obtener sesión activa por fight_id
    const { data: session, error: sessionErr } = await supabase
      .from("fight_telemetry_sessions")
      .select("id, fighter_red_id, fighter_blue_id")
      .eq("fight_id", fight_id)
      .eq("status", "active")
      .single();

    if (sessionErr || !session) {
      return json(
        { error: "No active session for this fight", detail: sessionErr?.message },
        404
      );
    }

    // 2. Resolver fighter_id desde corner (nunca enviado por el motor visión)
    const fighter_id =
      corner === "red" ? session.fighter_red_id : session.fighter_blue_id;

    // 3. Insertar en ai_strike_events (tabla canónica del contrato)
    const { error: insertErr } = await supabase
      .from("ai_strike_events")
      .insert({
        fight_id,
        session_id:  session.id,
        corner,
        fighter_id,
        strike_type,
        confidence:  Math.round((confidence as number) * 1000) / 1000,
      });

    if (insertErr) {
      return json(
        { error: "Failed to insert event", detail: insertErr.message },
        500
      );
    }

    return json({ ok: true });
  }

  // ── POST /stop ────────────────────────────────────────────────────────────
  if (suffix === "stop") {
    let body: { fight_id?: string; device_id?: string };
    try {
      body = await req.json();
    } catch {
      return json({ error: "Invalid JSON body" }, 400);
    }

    const { fight_id, device_id } = body;

    if (!fight_id || !device_id) {
      return json({ error: "fight_id and device_id are required" }, 400);
    }

    // Idempotente: si ya está ended, actualiza 0 filas y retorna 200 igualmente
    const { error: updateErr } = await supabase
      .from("fight_telemetry_sessions")
      .update({
        status:           "ended",
        ended_at:         new Date().toISOString(),
        vision_connected: false,
      })
      .eq("fight_id", fight_id)
      .eq("status", "active");

    if (updateErr) {
      return json(
        { error: "Failed to end session", detail: updateErr.message },
        500
      );
    }

    return json({ ok: true, fight_id });
  }

  // ── Ruta desconocida ──────────────────────────────────────────────────────
  return json(
    { error: "Unknown route. Available: /start, /event, /stop" },
    404
  );
});
