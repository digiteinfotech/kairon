## Agent: codebase-probe

### A1 Scheduler job-store consumer (Confidence: high)
- kairon/events/scheduler/kscheduler.py:9 imports apscheduler MongoDBJobStore; :80-84 builds ResilientBackgroundScheduler(jobstores={name: MongoDBJobStore(events_db, job_store_name, client)}); DB events.queue.name, collection events.scheduler.collection.
- schedule.py:~192-206 builds job_kwargs {version=1, trigger, executor="default", func, args, kwargs, id, name="execute_task", misfire_grace_time=7200, coalesce=True, next_run_time, max_instances=1}; :~228-233 insert_one({'_id','next_run_time','job_state': Binary(pickle.dumps(job_kwargs, HIGHEST_PROTOCOL))}).
- No unpickling code in kairon; stock APScheduler Job.__setstate__ reads it. Needs pickled apscheduler trigger instance + bound func ref. Non-Python writer cannot produce this.

### A2 /api/events/dispatch/{id} (Confidence: high)
events/server.py:151-154 -> KScheduler().dispatch_event(event_id) -> kscheduler.py:165-168 fires JobEvent(EVENT_JOB_ADDED) + scheduler.wakeup(). Does not read Mongo directly; wakeup triggers get_due_jobs() which unpickles. Returns {"data": None, "message": "Scheduled event dispatch!"}.

### A3 Plain-JSON scheduling endpoints (Confidence: high)
- POST /api/events/execute/{event_type}?is_scheduled=bool (server.py:124-132), body EventRequest (models.py:8-13) {data: {user, bot, ...}, cron_exp?, timezone?, run_at?}; PUT same (:135-143); DELETE /api/events/{event_id} (:146-148).
- utility.py:16-40 add_job: cron_exp -> add_job, run_at -> add_one_time_job. models.py:25-40: exactly one of cron_exp/run_at; scheduling allowed only for message_broadcast and analytics_pipeline.
- No generic endpoint to schedule an arbitrary callback/pyscript/flow. ActionSchedule's func is arbitrary; needs new event class or new endpoint.

### A4 Commit 8032de5c (Confidence: high)
Moved scheduler start out of KScheduler class body into event-server lifespan (server.py:60). Watchdog revives dead thread; _guard_update_job swallows JobLookupError. Did NOT change who writes jobs: ActionSchedule still inserts pickled docs directly (schedule.py:~228), which conflicts with "event server is only source of truth".

### G1 rasa_sdk message shape (Confidence: high)
rasa_sdk/executor.py:34-66 utter_message appends:
{"text": text, "buttons": buttons or [], "elements": elements or [], "custom": json_message or {}, "template": response, "response": response, "image": image, "attachment": attachment} then message.update(kwargs). All 8 keys always present. utter_message(None) -> {"text": None, "buttons": [], "elements": [], "custom": {}, "template": None, "response": None, "image": None, "attachment": None} still appended. Extra kwargs merged top-level. ActionExecutorRunResult (:173-177) {events, responses}; _create_api_response (:377-381).

### G2 Name casing (Confidence: high)
next_action NOT lowercased on webhook path (action.py:15-16 strip only; processor.py:34-37; utils.py:507-520, :530). Actions.clean lowercases on write only (data_objects.py:297-298). Mixed-case next_action -> "No action found for given bot and name". UTTER_PREFIX check case-sensitive.

### G3 Collection names (Confidence: high absence, med derived)
No meta collection overrides. Defaults: actions, action_server_logs, http_action_config, key_vault, bot_settings, slots (HttpActionConfig :151, ActionServerLogs :263, Slots data/data_objects.py:492, BotSettings :903, KeyVault :1006).

### G4 Webhook test expectations (Confidence: high)
- Missing action (~5725-5743): status 200, `{'events': [], 'responses': []}`, log exception == 'No action found for given bot and name'. Similar at 14584.
- Missing next_action (~5700-5703): status 200, response_json == None.
- 3776, 3939, 4276: responses == [] on failure cases.
- 422 handler server.py:185-192: Response(success=False, error_code=422, message=exc.errors()).dict() -> {success, error_code, message, data: None}, HTTP 200. No direct test found.
- server.py:315-332: ActionExecutionRejection/ActionNotFoundException -> 400 {"error","action_name"}.
