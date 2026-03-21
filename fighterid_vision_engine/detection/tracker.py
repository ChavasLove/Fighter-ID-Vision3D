"""
FighterID Vision Engine — SimpleTracker
Asignación de esquinas por posición horizontal.
Extraído de vision_motor_v1.py.
"""


class SimpleTracker:
    """
    Asigna esquinas a personas detectadas por posición horizontal.
    El luchador más a la izquierda = rojo, más a la derecha = azul.
    Suficiente para V1 — no requiere entrenamiento.
    """

    def assign(self, persons: list) -> dict:
        """
        Retorna {"red": person, "blue": person}.
        Puede ser un subconjunto si hay menos de 2 personas detectadas.
        """
        if not persons:
            return {}
        if len(persons) == 1:
            return {"red": persons[0]}
        # Ordenar por centro horizontal del bbox
        sorted_p = sorted(
            persons[:2],
            key=lambda p: (p["bbox"][0] + p["bbox"][2]) / 2,
        )
        return {"red": sorted_p[0], "blue": sorted_p[1]}
