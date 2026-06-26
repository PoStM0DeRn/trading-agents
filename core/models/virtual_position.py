from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class VirtualPositionModel(Base):
    __tablename__ = "virtual_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, ForeignKey("trades.trade_id"), unique=True)
    ticker = Column(String)

    trade = relationship("TradeModel", backref="virtual_positions")
    side = Column(String)
    quantity = Column(Integer)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    status = Column(String, default="open")
    opened_at = Column(String, default="CURRENT_TIMESTAMP")
    closed_at = Column(String)
    close_price = Column(Float)
    pnl = Column(Float, default=0)
    commission = Column(Float, default=0)
    strategy = Column(String)
    rationale = Column(Text)
    leverage = Column(Float, default=1.0)
    borrowed = Column(Float, default=0)
