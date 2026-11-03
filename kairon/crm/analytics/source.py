"""
Conversation selection for the lead pipeline. Reads Kairon's flattened conversation collection with the existing
`(bot, type, timestamp)` and `(bot, type, sender_id, timestamp)` indexes, always bounded by a time window and a limit.
"""
from typing import Any, Dict, List, Text, Tuple

from kairon.history.processor import HistoryProcessor
from kairon.shared.constants import FLATTENED_CONVERSATIONS

# `broadcast` rows are messages the bot pushed out; they say nothing about what the user wants.
USER_TURN_TYPE = "flattened"


class ConversationSource:

    @staticmethod
    def changed_senders(bot: Text, after_ts: float, until_ts: float, limit: int,
                        inclusive: bool = False) -> List[Tuple[Text, float]]:
        """
        Senders with at least one message in (after_ts, until_ts], oldest activity first, as (sender_id, newest_ts).
        Rows without a sender (anonymous or deleted) are ignored. `inclusive` makes the lower bound `>=` so a caller
        paging with the last timestamp it saw cannot skip senders that share it.
        """
        client = HistoryProcessor.get_mongo_connection()
        with client as client:
            coll = client.get_database().get_collection(FLATTENED_CONVERSATIONS)
            rows = coll.aggregate([
                {"$match": {"bot": bot, "type": USER_TURN_TYPE, "tag": {"$ne": "callback_message"},
                            "sender_id": {"$type": "string", "$ne": ""},
                            "timestamp": {("$gte" if inclusive else "$gt"): after_ts, "$lte": until_ts}}},
                {"$group": {"_id": "$sender_id", "last_ts": {"$max": "$timestamp"}}},
                {"$sort": {"last_ts": 1}},
                {"$limit": limit},
            ], allowDiskUse=False)
            return [(r["_id"], float(r["last_ts"])) for r in rows]

    @staticmethod
    def history(bot: Text, sender_id: Text, until_ts: float, max_turns: int) -> List[Dict[Text, Any]]:
        """Most recent `max_turns` turns up to `until_ts`, oldest first, as [{ts, user, bot}]."""
        client = HistoryProcessor.get_mongo_connection()
        with client as client:
            coll = client.get_database().get_collection(FLATTENED_CONVERSATIONS)
            rows = list(coll.find(
                {"bot": bot, "type": USER_TURN_TYPE, "sender_id": sender_id, "timestamp": {"$lte": until_ts}},
                {"_id": 0, "timestamp": 1, "data.user_input": 1, "data.bot_response": 1},
            ).sort("timestamp", -1).limit(max_turns))
        turns = []
        for row in reversed(rows):
            data = row.get("data") or {}
            bot_text = " ".join(
                (r.get("text") or "").strip() for r in (data.get("bot_response") or []) if isinstance(r, dict)
            ).strip()
            turns.append({"ts": float(row.get("timestamp") or 0), "user": data.get("user_input") or "", "bot": bot_text})
        return turns
