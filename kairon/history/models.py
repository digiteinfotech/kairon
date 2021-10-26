from fastapi import Query
from pydantic.main import BaseModel


class HistoryQuery(BaseModel):
    month: int = Query(default=1, ge=1, le=6)
    conversation_step_threshold: int = Query(default=10, ge=2)
    action_fallback: str = Query(default="action_default_fallback")
    nlu_fallback: str = Query(default=None)
    sort_by_date: bool = Query(default=True)
    top_n: int = Query(default=10, ge=1)
    l_bound: float = Query(default=0, ge=0, lt=1)
    u_bound: float = Query(default=1, gt=0, le=1)
    stopword_list: list = Query(default=None)
