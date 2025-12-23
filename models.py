from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Woreda(Base):
    __tablename__ = 'woredas'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    kebeles = relationship("Kebele", back_populates="woreda", cascade="all, delete-orphan")

class Kebele(Base):
    __tablename__ = 'kebeles'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    woreda_id = Column(Integer, ForeignKey('woredas.id'))
    woreda = relationship("Woreda", back_populates="kebeles")

class Farmer(Base):
    __tablename__ = 'farmers'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    f_type = Column(String)
    woreda = Column(String)
    kebele = Column(String)
    phone = Column(String)
    audio_url = Column(String)
    registered_by = Column(String)

def create_tables():
    from database import engine
    Base.metadata.create_all(engine)
