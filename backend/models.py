from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from db import Base


class PDF(Base):
    __tablename__ = "pdfs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), index=True)
    file_name = Column(String)
    storage_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    supabase_path = Column(String, nullable=True)

    summaries = relationship("Summary", back_populates="pdf")
    pdf_pages = relationship("PDF_Pages", back_populates="pdf")


class Summary(Base):
    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True, index=True)
    pdf_id = Column(Integer, ForeignKey("pdfs.id"))
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    pdf = relationship("PDF", back_populates="summaries")


class PDF_Pages(Base):
    __tablename__ = "pdf_pages"
    id = Column(Integer, primary_key=True, index=True)
    pdf_id = Column(Integer, ForeignKey("pdfs.id"))
    image_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    supabase_path = Column(String, nullable=True)
    page_number = Column(Integer)
    summary = Column(String)

    pdf = relationship("PDF", back_populates="pdf_pages")

class StickyNote(Base):
    __tablename__ = "sticky_notes"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(UUID(as_uuid=True), index=True)
    pdf_id     = Column(Integer, ForeignKey("pdfs.id", ondelete="CASCADE"))
    page_number = Column(Integer)
    text       = Column(Text, default="")
    x          = Column(Integer)          # px offset from page left
    y          = Column(Integer)          # px offset from page top
    color_idx  = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
 
    pdf = relationship("PDF")
 