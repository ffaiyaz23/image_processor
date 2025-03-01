# models.py
# SQLAlchemy models

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class ProcessingRequest(Base):
    __tablename__ = "processing_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, index=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    callback_url = Column(String, nullable=True)

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, ForeignKey("processing_requests.request_id"))
    serial_number = Column(String)
    product_name = Column(String)
    input_image_urls = Column(Text)
    output_image_urls = Column(Text, nullable=True)
    status = Column(String, default="pending")