from sqlalchemy import Column, Integer, String, Text
from core.database import Base


class ScanResultModel(Base):
    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_time = Column(String, default="CURRENT_TIMESTAMP")
    method = Column(String, default="filter")
    total_scanned = Column(Integer, default=0)
    filtered_count = Column(Integer, default=0)
    selected_count = Column(Integer, default=0)
    market_outlook = Column(String, default="neutral")
    selected_tickers = Column(Text, default="[]")
    all_candidates = Column(Text, default="[]")
