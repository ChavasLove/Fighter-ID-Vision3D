from supabase import create_client
import cv2

# =========================
# 🔐 CONFIGURACIÓN
# =========================
SUPABASE_URL = "https://eeshomcqztvjkvycdfwi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlc2hvbWNxenR2amt2eWNkZndpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYyNDUyMDAsImV4cCI6MjA3MTgyMTIwMH0.JbOPpqzJvzojVRP3hV4QuDeetzRVpRxoaZeBAXrCb2c"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================
# 🧠 FORMATEO DE PELEADOR
# =========================
def formatear_peleador(f):
    nombre = f"{f.get('first_name', '')} {f.get('last_name', '')}".strip()
    nickname = f.get("nickname") or ""

    return {
        "id": f.get("id"),
        "nombre": nombre,
        "nickname": nickname,
        "gym": f.get("gym_name"),
        "record": f"{f.get('record_wins',0)}-{f.get('record_losses',0)}-{f.get('record_draws',0)}",
        "disciplina": f.get("discipline"),
        "foto": f.get("avatar_url")
    }


# =========================
# 🔍 BUSCAR PELEADOR
# =========================
def buscar_peleador(nombre):
    response = supabase.table("fighter_profiles") \
        .select("*") \
        .ilike("first_name", f"%{nombre}%") \
        .execute()

    return [formatear_peleador(f) for f in response.data]


# =========================
# 🎯 SELECCIONAR PELEADOR
# =========================
def seleccionar_peleador():
    while True:
        nombre = input("🔍 Buscar peleador: ")
        resultados = buscar_peleador(nombre)

        if not resultados:
            print("❌ No se encontraron resultados")
            continue

        print("\nResultados:\n")

        for i, r in enumerate(resultados):
            print(f"[{i}] {r['nombre']} ({r['record']}) - {r['gym']}")

        while True:
            seleccion = input("\nSelecciona índice: ")

            if not seleccion.isdigit():
                print("⚠️ Ingresa un número válido")
                continue

            seleccion = int(seleccion)

            if seleccion < 0 or seleccion >= len(resultados):
                print("⚠️ Índice fuera de rango")
                continue

            return resultados[seleccion]


# =========================
# 🧠 CONTEXTO DE PELEA
# =========================
def crear_contexto_pelea(fighter_a, fighter_b):
    return {
        "fighter_a_id": fighter_a["id"],
        "fighter_b_id": fighter_b["id"],
        "fighter_a_nombre": fighter_a["nombre"],
        "fighter_b_nombre": fighter_b["nombre"]
    }


# =========================
# 🎥 OVERLAY VIDEO
# =========================
def iniciar_camara(contexto):
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("❌ No se pudo abrir la cámara")
        return

    print("\n🎥 Cámara iniciada (presiona Q para salir)\n")

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        # 🟥 Fighter A (izquierda)
        cv2.putText(
            frame,
            contexto["fighter_a_nombre"],
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2
        )

        # 🟦 Fighter B (derecha)
        cv2.putText(
            frame,
            contexto["fighter_b_nombre"],
            (800, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 0, 0),
            2
        )

        cv2.imshow("Fighter ID Vision", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


# =========================
# 🚀 MAIN
# =========================
def main():
    print("===================================")
    print("🥊 FIGHTER ID SYSTEM")
    print("===================================\n")

    fighter_a = seleccionar_peleador()
    fighter_b = seleccionar_peleador()

    print("\n🔥 PELEA CONFIGURADA:\n")
    print("Fighter A:", fighter_a["nombre"])
    print("Fighter B:", fighter_b["nombre"])

    contexto = crear_contexto_pelea(fighter_a, fighter_b)

    print("\n🧠 CONTEXTO:", contexto)

    iniciar_camara(contexto)


# =========================
# ▶️ EJECUCIÓN
# =========================
if __name__ == "__main__":
    main()