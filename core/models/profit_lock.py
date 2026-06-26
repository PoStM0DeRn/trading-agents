from sqlalchemy import Column, Integer, String, Float
from core.database import Base


class ProfitLockModel(Base):
    __tablename__ = "profit_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    locked_at = Column(String, default="CURRENT_TIMESTAMP")
    equity = Column(Float)
    initial_capital = Column(Float)
    target_percent = Column(Float)
    target_equity = Column(Float)
    positions_closed = Column(Integer, default=0)
    total_pnl = Column(Float, default=0)
    unlock_after_cycle = Column(Integer, default=0)
    status = Column(String, default="active")
