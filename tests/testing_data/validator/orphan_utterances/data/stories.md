## greet
* greet
  - utter_greet
  - action_restart

## say goodbye
* deny
  - utter_goodbye
  - action_restart

## apply
* apply
  - intent: apply
  - action: reset slots
  - action: job_apply
  - action: utter_slot_details
