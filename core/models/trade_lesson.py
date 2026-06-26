from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class TradeLessonModel(Base):
    __tablename__ = "trade_lessons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, ForeignKey("trades.trade_id"))
    trade = relationship("TradeModel", backref="lessons")
    ticker = Column(String)
    strategy = Column(String)
    lesson_type = Column(String)
    pattern_description = Column(Text)
    conditions = Column(Text)
    confidence = Column(Float)
    times_observed = Column(Integer)
    times_lost = Column(Integer)
    win_rate = Column(Float)
    severity = Column(String)
    created_at = Column(String, default="CURRENT_TIMESTAMP")
    last_updated = Column(String, default="CURRENT_TIMESTAMP")
