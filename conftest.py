# Archivo vacío a propósito: su sola presencia en la raíz hace que pytest
# agregue el rootdir a sys.path sin importar cómo se invoque (pytest, python
# -m pytest, un IDE), evitando el ModuleNotFoundError: No module named 'motor'.
