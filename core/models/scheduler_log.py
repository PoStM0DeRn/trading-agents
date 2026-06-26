from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from core.database import Base


class SchedulerLogModel(Base):
    __tablename__ = "scheduler_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(String)
    cycle_id_int = Column(Integer, ForeignKey("trades.id"))
    timestamp = Column(String)
    tickers = Column(Text)
    proposals = Column(Integer)
    approved = Column(Integer)
    executed = Column(Integer)
    errors = Column(Integer)
    error_msg = Column(Text)
    capital = Column(Float)
