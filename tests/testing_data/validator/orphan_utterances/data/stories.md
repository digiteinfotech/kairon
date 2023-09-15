## greet
* greet
  - utter_greet
  - action_restart

## say goodbye
* deny
  - utter_goodbye
  - action_restart
  - google_search_action

## apply
* apply
  - intent: apply
  - action: reset slots
  - action: job_apply
  - action: utter_slot_details
