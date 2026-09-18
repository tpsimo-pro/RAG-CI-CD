"""
Ordem determinística dos resultados de busca.

A fusão RRF produz scores que são somas de frações pequenas, então empates
exatos são comuns — no piloto, 40 das 300 linhas tinham empate no top-5. O
Qdrant desempata de forma arbitrária: os scores voltam sempre iguais, mas a
ordem entre empatados, e qual empatado sobrevive ao corte, mudam entre
execuções. Isso tornava a recuperação não reprodutível.

O desempate passa a ser nosso, por (source, section, id), aplicado sobre o
conjunto completo de candidatos fundidos — não sobre um top-k já cortado pelo
servidor, que é onde o empate era decidido às escondidas.
"""

from __future__ import annotations

from rag_reviewer.vector_store import ordenar_deterministico


def ponto(score: float, source: str, section: str, id_: str) -> dict:
    return {
        "text": f"norma {section}",
        "source": source,
        "section": section,
        "page": 0,
        "score": score,
        "id": id_,
    }


class TestOrdenarDeterministico:
    def test_score_maior_vem_primeiro(self):
        a = ponto(0.5, "guia.md", "1.1", "id-a")
        b = ponto(0.9, "guia.md", "2.2", "id-b")

        assert ordenar_deterministico([a, b], top_k=2) == [b, a]

    def test_empate_e_desempatado_por_source_e_section(self):
        """Mesmo score: a ordem não pode depender de quem o servidor mandou primeiro."""
        z = ponto(0.25, "z_guia.md", "1.1", "id-z")
        a = ponto(0.25, "a_guia.md", "9.9", "id-a")

        assert ordenar_deterministico([z, a], top_k=2) == [a, z]
        # a ordem de ENTRADA invertida produz a MESMA saída
        assert ordenar_deterministico([a, z], top_k=2) == [a, z]

    def test_empate_no_mesmo_documento_desempata_por_section(self):
        b = ponto(0.5, "guia.md", "2.2 Booleanos", "id-b")
        a = ponto(0.5, "guia.md", "1.1 Nulos", "id-a")

        assert ordenar_deterministico([b, a], top_k=2) == [a, b]

    def test_empate_total_desempata_por_id(self):
        """
        Dois chunks do mesmo documento e da mesma seção ainda precisam de
        ordem total, senão o empate volta a ser decidido pelo servidor.
        """
        segundo = ponto(0.5, "guia.md", "5", "id-b")
        primeiro = ponto(0.5, "guia.md", "5", "id-a")

        assert ordenar_deterministico([segundo, primeiro], top_k=2) == [
            primeiro,
            segundo,
        ]

    def test_corte_no_top_k_e_deterministico_entre_empatados(self):
        """
        O caso que mais dói: dois candidatos empatados disputam a última vaga.
        Quem entra não pode depender da ordem em que o servidor os devolveu.
        """
        alto = ponto(0.9, "guia.md", "1", "id-1")
        empatado_x = ponto(0.25, "x_guia.md", "4", "id-x")
        empatado_y = ponto(0.25, "y_guia.md", "7", "id-y")

        # uma vaga só além do primeiro: x deve ganhar nas duas ordens de entrada
        assert ordenar_deterministico([alto, empatado_y, empatado_x], top_k=2) == [
            alto,
            empatado_x,
        ]
        assert ordenar_deterministico([alto, empatado_x, empatado_y], top_k=2) == [
            alto,
            empatado_x,
        ]

    def test_top_k_maior_que_a_lista_devolve_tudo(self):
        a = ponto(0.5, "guia.md", "1", "id-a")

        assert ordenar_deterministico([a], top_k=5) == [a]

    def test_lista_vazia(self):
        assert ordenar_deterministico([], top_k=5) == []
