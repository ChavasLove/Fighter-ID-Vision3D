/**
 * FighterID — Edge Function: get-fight-context
 *
 * Retorna el contexto completo de un combate (peleadores, gimnasios,
 * categoría, récord) en el formato que espera el motor visión.
 *
 * URL: https://<project>.supabase.co/functions/v1/get-fight-context?fight_id=<uuid>
 *
 * Requiere: view fight_full_context aplicada (migrations/fight_full_context.sql)
 *
 * Deploy:
 *   supabase functions deploy get-fight-context
 */

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req: Request) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  const { searchParams } = new URL(req.url);
  const fightId = searchParams.get("fight_id");

  if (!fightId) {
    return new Response(
      JSON.stringify({ error: "Parámetro requerido: fight_id" }),
      { status: 400, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }
    );
  }

  // Usar service role key para leer la view sin restricciones RLS
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } }
  );

  const { data, error } = await supabase
    .from("fight_full_context")
    .select("*")
    .eq("fight_id", fightId)
    .single();

  if (error) {
    const status = error.code === "PGRST116" ? 404 : 500;
    return new Response(
      JSON.stringify({ error: error.message, code: error.code }),
      { status, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }
    );
  }

  // Normalizar al formato dict que espera el motor visión Python
  const result = {
    fight_id:  data.fight_id,
    event_id:  data.event_id,
    status:    data.status,
    lifecycle: data.lifecycle,

    fighter_red: {
      id:           data.fighter_red_id,
      name:         data.fighter_red_name,
      nickname:     data.fighter_red_nickname,
      record:       data.fighter_red_record,
      weight_class: data.fighter_red_weight,
      gym:          data.fighter_red_gym,
    },

    fighter_blue: {
      id:           data.fighter_blue_id,
      name:         data.fighter_blue_name,
      nickname:     data.fighter_blue_nickname,
      record:       data.fighter_blue_record,
      weight_class: data.fighter_blue_weight,
      gym:          data.fighter_blue_gym,
    },
  };

  return new Response(
    JSON.stringify(result),
    { headers: { ...CORS_HEADERS, "Content-Type": "application/json" } }
  );
});
