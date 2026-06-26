from sqlalchemy import Column, Integer, String, Text
from core.database import Base


class AgentLogModel(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String)
    action = Column(String)
    input_data = Column(Text)
    output_data = Column(Text)
    tool_calls = Column(Text)
    timestamp = Column(String, default="CURRENT_TIMESTAMP")
