from sqlalchemy import Column, Integer, String, Text
from core.database import Base


class ConfigAuditModel(Base):
    __tablename__ = "config_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, default="CURRENT_TIMESTAMP")
    section = Column(String)
    param = Column(String)
    old_value = Column(Text)
    new_value = Column(Text)
    source = Column(String, default="dashboard")
