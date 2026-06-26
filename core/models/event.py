from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from core.database import Base


class EventModel(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String)
    ticker = Column(String, ForeignKey("trades.ticker"))
    description = Column(Text)
    impact_score = Column(Float)
    sentiment = Column(String)
    source = Column(String)
    timestamp = Column(String)
    created_at = Column(String, default="CURRENT_TIMESTAMP")
