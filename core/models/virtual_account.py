from sqlalchemy import Column, Integer, Float, String
from core.database import Base


class VirtualAccountModel(Base):
    __tablename__ = "virtual_account"

    id = Column(Integer, primary_key=True, autoincrement=True)
    initial_capital = Column(Float, default=100000)
    current_balance = Column(Float, default=100000)
    borrowed = Column(Float, default=0)
    updated_at = Column(String, default="CURRENT_TIMESTAMP")
