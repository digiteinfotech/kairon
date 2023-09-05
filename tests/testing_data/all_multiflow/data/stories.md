## greet
* greet
  - utter_offer_help
  - action_restart

## say goodbye
* goodbye
  - utter_goodbye
  - action_restart

## thank from user
* thank
  - utter_welcome_message
  - action_restart

## Case 1.1: Log ticket with attachment required 
* log_ticket
  - action_identify_ticket_attributes
  - utter_ticket_attributes
* affirm
  - utter_attachment_upload
* affirm OR affirm_attachment
  - action_clear_file
  - ticket_file_form
  - slot{"priority":"High"}
  - form{"name":"ticket_file_form"}
  - form{"name":null}
  - action_log_ticket
  - action_restart

## Case 1.2: Log ticket with attachment not required 
* log_ticket
  - action_identify_ticket_attributes
  - utter_ticket_attributes
* affirm
  - utter_attachment_upload
* deny
  - action_log_ticket
  - action_restart

## Case 1.3: Log ticket with attachment and Priority Change
* log_ticket
  - action_identify_ticket_attributes
  - utter_ticket_attributes
* deny
  - action_clear_priority
  - ticket_attributes_form
  - form{"name":"ticket_attributes_form"}
  - form{"name":null}
  - utter_attachment_upload
* affirm
  - action_clear_file
  - ticket_file_form
  - form{"name":"ticket_file_form"}
  - form{"name":null}
  - action_log_ticket
  - action_restart

## Case 1.4: Log ticket without attachment and Priority Change
* log_ticket
  - action_identify_ticket_attributes
  - utter_ticket_attributes
* deny
  - action_clear_priority
  - ticket_attributes_form
  - form{"name":"ticket_attributes_form"}
  - form{"name":null}
  - utter_attachment_upload
* deny
  - action_log_ticket
  - action_restart

## Case 3.1: Get ticket status - #Ticketid valid  
* get_ticket_status
  - action_validate_ticket_for_status
  - action_get_ticket_status
  - action_restart

## Case 4.0: Get procurement list  
* get_procurement_tickets
  - utter_procurement
* affirm 
  - utter_procurement_approved
  - action_restart

## Case 4.1: Get procurement list  
* get_procurement_tickets
  - utter_procurement
* deny 
  - utter_procurement_rejected
  - action_restart

## small talk
* small_talk
  - action_small_talk
  - action_restart
  
## greet again
* greet_again
  - utter_greet
  - action_restart

## feedback good
* performance_feedback
  - utter_feedback
* user_feedback{"fdResponse":"like"}
   - utter_good_feedback

## feedback bad
* performance_feedback
  - utter_feedback
* user_feedback{"fdResponse":"hate"}
   - utter_bad_feedback