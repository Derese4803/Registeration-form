from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# connect_args is needed for SQLite to work with Streamlit's multi-threading
engine = create_engine('sqlite:///survey.db', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
