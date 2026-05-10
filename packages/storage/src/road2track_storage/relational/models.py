"""Modèles SQLAlchemy 2 (style 2.0) pour la persistance applicative.

Cf. specs/06-modele-donnees.md §7. Schéma minimal au démarrage : projects + segments.
Tile / Track / CoverageVoxel viendront avec les itérations suivantes.

Compatibilité Postgres + SQLite : on utilise `JSON` (pas `JSONB`) pour le champ
métadonnées. Les tests unitaires peuvent ainsi tourner sur SQLite in-memory.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base déclarative SQLAlchemy 2 pour tous les modèles applicatifs."""


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    origin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_alt: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    segments: Mapped[list[SegmentRow]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class SegmentRow(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    fps: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_lidar: Mapped[bool] = mapped_column(default=True, nullable=False)
    raw_paths: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped[ProjectRow] = relationship(back_populates="segments")
