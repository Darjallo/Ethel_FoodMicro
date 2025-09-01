from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid
import datetime


class EthelDocument(SQLModel, table=True):
    __tablename__ = "etheldocuments"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True),
    )
    title: str
    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, nullable=False
    )
    content_type: str = Field(
        default="application/octet-stream",
        nullable=False,
        sa_column_kwargs={"server_default": "application/octet-stream"},
    )

    chunk_sets: List["ChunkSet"] = Relationship(back_populates="document")


class ChunkSet(SQLModel, table=True):
    __tablename__ = "chunksets"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True),
    )
    document_id: uuid.UUID = Field(foreign_key="etheldocuments.id", nullable=False)
    method: str  # e.g. "sliding_window_500"
    created_at: Optional[str] = Field(default=None)

    document: EthelDocument = Relationship(back_populates="chunk_sets")
    chunks: List["Chunk"] = Relationship(
        back_populates="chunk_set", cascade_delete=True
    )


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True),
    )
    chunk_set_id: uuid.UUID = Field(
        foreign_key="chunksets.id", nullable=False, ondelete="CASCADE"
    )
    text: str
    position: int

    chunk_set: ChunkSet = Relationship(back_populates="chunks")


class EmbeddingModel(SQLModel, table=True):
    __tablename__ = "embedding_models"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True),
    )
    name: str  # e.g. "text-embedding-3-large"
    dimension: int
    table_name: str  # the actual embedding table to use (managed separately)


class TextEmbedding3LargeEmbedding(SQLModel, table=True):
    __tablename__ = "embeddings_text_embedding_3_large"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True),
    )
    chunk_id: uuid.UUID = Field(foreign_key="chunks.id", nullable=False)
    vector: List[float] = Field(
        sa_column=Column(Vector(3072))
    )  # dimension fixed per model
    created_at: Optional[str] = Field(default=None)


# class QwenMathEmbedding(SQLModel, table=True):
#     __tablename__ = "embeddings_qwen_math"

#     id: uuid.UUID = Field(
#         default_factory=uuid.uuid4,
#         sa_column=Column(UUID(as_uuid=True), primary_key=True),
#     )
#     chunk_id: uuid.UUID = Field(foreign_key="chunks.id", nullable=False)
#     vector: List[float] = Field(
#         sa_column=Column(Vector(4096))
#     )  # dimension fixed per model
#     created_at: Optional[str] = Field(default=None)


# class DocumentCourseLink(SQLModel, table=True):
#     __tablename__ = "document_course_links"

#     document_id: uuid.UUID = Field(
#         foreign_key="etheldocuments.id", primary_key=True, nullable=False
#     )
#     course_id: uuid.UUID = Field(
#         foreign_key="courses.id", primary_key=True, nullable=False
#     )


# class Course(SQLModel, table=True):
#     __tablename__ = "courses"

#     id: uuid.UUID = Field(
#         default_factory=uuid.uuid4,
#         sa_column=Column(UUID(as_uuid=True), primary_key=True),
#     )
#     name: str

#     documents: List[EthelDocument] = Relationship(
#         back_populates="courses", link_model=DocumentCourseLink
#     )
