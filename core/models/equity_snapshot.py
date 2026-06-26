from sqlalchemy import Column, Integer, String, Float
from core.database import Base


class EquitySnapshotModel(Base):
    __tablename__ = "equity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, default="CURRENT_TIMESTAMP")
    total_value = Column(Float)
    balance = Column(Float)
    positions_value = Column(Float)
    pnl = Column(Float)
    borrowed = Column(Float)
    margin_level = Column(Float)
    positions_count = Column(Integer)
    cycle_id = Column(String)
