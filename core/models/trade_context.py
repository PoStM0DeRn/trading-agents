from sqlalchemy import Column, String, Float
from core.database import Base


class TradeContextModel(Base):
    __tablename__ = "trade_context"

    trade_id = Column(String, primary_key=True)
    ticker = Column(String)
    rsi = Column(Float)
    macd_signal = Column(String)
    bb_position = Column(String)
    atr = Column(Float)
    volatility_regime = Column(String)
    trend = Column(String)
    volume_vs_avg = Column(Float)
    sentiment_score = Column(Float)
    sentiment_label = Column(String)
    support = Column(Float)
    resistance = Column(Float)
    price_at_entry = Column(Float)
    created_at = Column(String, default="CURRENT_TIMESTAMP")
