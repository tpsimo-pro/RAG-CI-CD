"""Converte o reST da PEP 8 em Markdown para o corpus indexado.

Uso: python scripts/pep8_rst_to_md.py pep-0008.rst pep-0008.md

Fonte: https://github.com/python/peps (peps/pep-0008.rst), commit
5514795ade79a5bf6f3c08c562b02689d0a9feb2. O texto nao e alterado; so a
marcacao muda (cabecalhos, blocos de codigo, literais, referencias).
"""
import re
import sys

HEADING = {"=": "##", "-": "###", "~": "####"}
FENCED = re.compile(r"(^ *```python\n.*?^ *```$)", re.DOTALL | re.MULTILINE)


def inline(text):
    """Converte a marcacao inline do reST em Markdown."""
    text = re.sub(
        r":pep:`([^`<]*?)\s*<(\d+)[^>]*>`", r"\1 (PEP \2)", text, flags=re.S
    )
    text = re.sub(r":pep:`(\d+)`", r"PEP \1", text)
    text = re.sub(r"(?<!`)`([^`]+?)`_(?!_)", r"\1", text)
    text = re.sub(r"``(.+?)``", r"`\1`", text, flags=re.S)
    text = re.sub(r"\[#fn-(\w+)\]_", r"[fn-\1]", text)
    return re.sub(r"\[(\d+)\]_", r"[\1]", text)


def convert(lines):
    """Converte as linhas do reST (a partir de Introduction) em Markdown."""
    out = []
    i = lines.index("Introduction")
    n = len(lines)
    while i < n:
        line = lines[i]
        under = lines[i + 1] if i + 1 < n else ""
        is_heading = (
            under
            and set(under) <= set(HEADING)
            and len(under) >= len(line) > 0
            and line[0] not in " ."
        )
        if is_heading:
            out += [f"{HEADING[under[0]]} {line}", ""]
            i += 2
        elif line.lstrip().startswith(".. code-block::"):
            indent = " " * (len(line) - len(line.lstrip()))
            i += 1
            while lines[i].strip().startswith(":") or not lines[i].strip():
                i += 1
            block = []
            while i < n and (
                lines[i].startswith(indent + "   ") or not lines[i].strip()
            ):
                body = lines[i][len(indent) + 3:] if lines[i].strip() else ""
                block.append(indent + body if body else "")
                i += 1
            while block and not block[-1].strip():
                block.pop()
            out += [indent + "```python", *block, indent + "```", ""]
        elif line.startswith(".. _"):
            i += 1
        elif line.startswith(".. rubric::"):
            out += ["## Footnotes", ""]
            i += 1
        else:
            note = re.match(r"\.\. \[#?(?:fn-)?(\w+)\] (.*)", line)
            if note:
                key = note.group(1)
                key = key if key.isdigit() else f"fn-{key}"
                out.append(f"[{key}] {note.group(2)}")
                i += 1
                while i < n and lines[i].startswith("   "):
                    out.append(lines[i].strip())
                    i += 1
                out.append("")
            else:
                out.append(line)
                i += 1
    return out


def main(src, dst):
    """Le o reST em `src` e grava o Markdown em `dst`."""
    with open(src, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    text = "\n".join(convert(lines))
    parts = FENCED.split(text)
    text = "".join(
        part if part.lstrip().startswith("```python") else inline(part)
        for part in parts
    )
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    with open(dst, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
