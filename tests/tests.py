import unittest
from src.utils.data_handler import stringify_keys


# Función auxiliar para encontrar claves que no son strings (originalmente en helpers.py para send_to_fastapi)
def find_non_str_keys(obj, path="root"):
    bad = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                bad.append((path + f"/{repr(k)}", type(k).__name__))
            bad.extend(find_non_str_keys(v, path + f"/{repr(k)}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(find_non_str_keys(v, path + f"[{i}]"))
    return bad


class TestDataHandler(unittest.TestCase):
    def test_stringify_keys_basic(self):
        # Caso: Diccionario con enteros
        data = {1: "uno", 2: "dos"}
        result = stringify_keys(data)

        # Aserción: Verificamos que las claves sean strings
        self.assertEqual(result, {"1": "uno", "2": "dos"})

        # Aserción usando tu herramienta de diagnóstico (debe devolver lista vacía)
        self.assertEqual(find_non_str_keys(result), [])

    def test_stringify_keys_nested(self):
        # Caso: Anidado con None y tipos mixtos
        data = {
            "usuario": "Juan",
            "meta": {None: "valor nulo", "null": "texto null", 10: [1, 2]},
        }
        result = stringify_keys(data)

        # Verificamos transformaciones específicas
        self.assertIn("None", result["meta"])  # None -> "None"
        self.assertEqual(result["meta"]["None"], "valor nulo")

        # Verificamos que no queden claves malas
        self.assertEqual(find_non_str_keys(result), [])


if __name__ == "__main__":
    unittest.main()
