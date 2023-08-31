import nbformat


def read_as_notebook(notebook_json_str: str, /, *, as_version: int = 4):
    return nbformat.reads(notebook_json_str, as_version=as_version)


def normalize_notebook(notebook_json_str: str) -> str:
    """Jupyter Notebook 形式のJSON文字列を受け取り、正規化したJSON文字列を返す"""
    notebook = nbformat.reads(notebook_json_str, nbformat.NO_CONVERT)
    return nbformat.writes(notebook)
