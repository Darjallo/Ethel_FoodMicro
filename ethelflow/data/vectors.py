from typing import List

from pgvector.sqlalchemy import Vector
from sqlmodel import Session, cast, func, select

from ethelflow.data.models import (
    Chunk,
    ChunkSet,
    EthelDocument,
    TextEmbedding3LargeEmbedding,
)

# def get_embeddings_by_chunk_ids(
#     session: Session, chunk_ids: List[str]
# ) -> List[TextEmbedding3LargeEmbedding]:
#     statement = select(TextEmbedding3LargeEmbedding).where(
#         TextEmbedding3LargeEmbedding.chunk_id.in_(chunk_ids)
#     )
#     results = session.exec(statement).all()
#     return results


# Retrieve the most relevant chunks based on a query vector
def get_relevant_chunks(session: Session, query_vector: List[float], top_k: int = 5):
    query_vec_expr = cast(query_vector, Vector(3072))
    distance = func.cosine_distance(
        TextEmbedding3LargeEmbedding.vector, query_vec_expr
    ).label("distance")

    stmt = (
        select(Chunk.text, EthelDocument.title, distance)
        .join(Chunk, Chunk.id == TextEmbedding3LargeEmbedding.chunk_id)
        .join(ChunkSet, ChunkSet.id == Chunk.chunk_set_id)
        .join(EthelDocument, EthelDocument.id == ChunkSet.document_id)
        .order_by(distance)
        .limit(top_k)
    )

    results = session.exec(stmt).all()
    return [{"text": r.text, "title": r.title, "distance": r.distance} for r in results]
