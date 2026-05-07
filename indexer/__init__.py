"""
indexer — Pipeline offline de indexação do guia de estilo.

Responsável por:
  1. Carregar documentos (PDF, Markdown, DOCX)
  2. Dividir em chunks com sobreposição
  3. Gerar embeddings
  4. Inserir no Qdrant
"""
