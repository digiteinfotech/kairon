import sys
import json
import traceback
from functools import partial
import os

from mongoengine import connect, disconnect

from kairon import Utility
from kairon.shared.concurrency.actors.utils import PyscriptUtility
from kairon.shared.pyscript.shared_pyscript_utils import PyscriptSharedUtility
from kairon.shared.pyscript.callback_pyscript_utils import CallbackScriptUtility


def _cleanup_and_exit(exit_code: int):
    """
    Ensures all buffers are flushed, DB disconnected, and process exits cleanly.
    """
    try:
        disconnect()
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(exit_code)


def main():
    exit_code = 0
    try:
        raw = sys.stdin.readline().strip()
        data = json.loads(raw)
        db_url = Utility.environment['database']["url"]
        config = Utility.mongoengine_connection(db_url)
        connect(**config)
        source_code = data.get("source_code", "")
        predefined = data.get("predefined_objects", {})
        safe_globals = data.get("safe_globals", {})
        bot = data.get("bot")

        if isinstance(safe_globals, list):
            allowed = {
                "add_data": partial(PyscriptSharedUtility.add_data, bot=bot),
                "get_data": partial(PyscriptSharedUtility.get_data, bot=bot),
                "delete_data": partial(PyscriptSharedUtility.delete_data, bot=bot),
                "update_data": partial(PyscriptSharedUtility.update_data, bot=bot),
                "add_data_analytics": partial(CallbackScriptUtility.add_data_analytics, bot=bot),
                "get_data_analytics": partial(CallbackScriptUtility.get_data_analytics, bot=bot),
                "mark_as_processed": partial(CallbackScriptUtility.mark_as_processed, bot=bot),
                "update_data_analytics": partial(CallbackScriptUtility.update_data_analytics, bot=bot),
                "delete_data_analytics": partial(CallbackScriptUtility.delete_data_analytics, bot=bot),
                "srtp_time": PyscriptUtility.srtptime,
                "srtf_time": PyscriptUtility.srtftime,
                "url_parse": PyscriptUtility.url_parse_quote_plus,
                "__builtins__": __builtins__,
            }
            converted = {k: allowed[k] for k in safe_globals if k in allowed}
            safe_globals = converted

        if "__builtins__" not in safe_globals:
            safe_globals["__builtins__"] = __builtins__

        local_vars = predefined.copy()
        exec(source_code, safe_globals, local_vars)
        result = {k: v for k, v in local_vars.items() if not k.startswith("__")}
        print(json.dumps({"success": True, "data": result}, default=str), flush=True)

    except Exception as e:
        exit_code = 1
        print(json.dumps({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), flush=True)

    finally:
        _cleanup_and_exit(exit_code)

if __name__ == "__main__":
    main()
