# create_tables.py
# Script to create database tables

from app.database import engine
from app.models import Base

def create_tables():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    create_tables()
