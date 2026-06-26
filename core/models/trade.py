from sqlalchemy import Column, Integer, String, Float, Text
from core.database import Base


class TradeModel(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, unique=True, nullable=False)
    ticker = Column(String, nullable=False)
    action = Column(String)
    quantity = Column(Integer)
    entry_price = Column(Float)
    exit_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    pnl = Column(Float)
    commission = Column(Float)
    strategy = Column(String)
    signal_context = Column(Text)
    rationale = Column(Text)
    opened_at = Column(String)
    closed_at = Column(String)
    status = Column(String)
    created_at = Column(String, default="CURRENT_TIMESTAMP")
