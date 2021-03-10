## intent:greet
- hey
- hello
- hi
- good morning
- good evening
- hey there
- watsup
- howdy

## intent:deny
- no
- never
- I don't think so
- don't like that
- no way
- not really
- nope
- modify the priority
- just change the priority
- i don't agree with this priority
- not now
- not required
- forget it
- not needed
- not relevant
- maybe later
- later
- change the priority please
- modify the priority please
- change the priority
- change priority
- modify priority

## intent:log_ticket
- I am getting error while connecting to VPN.
- I am not able to connect to demo application from office desktop.
- My laptop battery is getting drained too quickly.
- Need to increase machine RAM for installing SOLR setup.
- My laptop screen is showing black spots.
- My laptop mouse pad giving trouble.
- I need LDAP Sever on AWS for automation run.
- I need oracle client installed on my laptop.
- Can anyone look into Sahi Pro installation for my laptop?
- I need access to coursera portal for AI related courses.
- I require youtube access for watching share point tutorials.
- There is a virus attack on my laptop
- There seems a virus attack on my laptop
- virus attack
- My computer has had a virus attack
- Enable notification of Dhruva
- Symantec Antivirus is not working
- Not able to sent mails via outlook
- Issue with weblogic10 server
- Skype - Installation
- Incomplete mails in outlook.
- Emails are failing
- Headphones replacement
- Issue with microsoft word
- USB Mouse required
- Desktop freezes / Hang-up
- Outlook Error
- Access rights for Automation setup
- Installation of oracle
- VSS to be installed on machine
- JBOSS Required
- Issue With Msp
- unable to login to VSS
- Please download the oracle11g
- jdk 1.5 installation
- Unable to Print from my machine
- Headset and mic is not working properly
- Create database security policy

## intent:affirm
- yes
- correct
- affirmative that is fine yes
- sure, please go ahead
- that is good
- yes sir
- affirmative
- ya
- fine
- ok
- agreed
- agreed yep
- right
- yup
- go ahead
- done
- ok done
- affirmative please
- yep
- sounds good
- sounds good right
- yes sir please
- yes sounds good
- yep that is good
- i am ok with that
- yep that is correct
- yes right
- yes correct
- yes you understood me i am ok with that
- correct sir thank you
- i am ok with that
- affirmative right
- agreed yep
- indeed
- of course
- that sounds good
- yes now
- yes required
- required
- needed it
- it is relevant
- sure
- ya why not
- yes please
- ya sure
- ya please
- yes go ahead
- go ahead
- yes looks fine
- ya sounds good
- yes sounds good
- yes looks ok to me
- good suggestion

## intent:log_ticket_with_attributes
- My laptop is not working, log a [critical priority](priority) [hardware issue](category) ticket
- My laptop is not working, log a [critical](priority) [hardware issue](category) ticket

## intent:get_priority
- [Critical Priority](priority)
- [Critical](priority)
- [High](priority)
- [Medium](priority)
- [Low](priority)
- [critical priority](priority)
- [critical](priority)
- [high](priority)
- [medium](priority)
- [low](priority)
- Log a [critical issue](priority)
- Log a [high issue](priority)
- Log a [medium issue](priority)
- Log a [low issue](priority)
- [High Priority](priority)
- [Medium Priority](priority)
- [Low Priority](priority)
- no, this issue is a [showstopper](priority) for me, my work is stuck
- no, this issue is a [showstopper](priority)
- log a [critical issue](priority)
- I need this to be logged as a [critical issue](priority)
- change priority to [critical](priority)
- I need it [asap](priority)
- this is [urgent](priority)
- this is [showstopper](priority)
- log it as [medium](priority)
- make it [medium](priority)
- change priority to [medium](priority)
- this can be considered as [medium](priority)

## synonym:critical
- urgent
- showstopper
- asap

## intent:file_upload
- Test File
- Attachment

## intent:get_ticketID
- [TKT456](ticketID)
- [TKT234](ticketID)
- [TKT123](ticketID)
- [TKT789](ticketID)
- [TKT677](ticketID)
- [TKT777](ticketID)
- [TKT546](ticketID)
- [TKT789](ticketID)
- [TKT4566](ticketID)
- I want to upload a document against my ticket [TKT456]
- can you upload a file for [TKT456](ticketID)
- i need to upload a doc against [TKT123](ticketID)
- hey, attach a document against [TKT789](ticketID)
- can you attach a doc on [TKT677](ticketID)
- can you load a doc on [TKT234](ticketID)
- i need to load a doc against [TKT546](ticketID)
- please upload a doc file against [TKT789](ticketID)

## intent:valid_ticketID
- my bad, the id is [TKT456](ticketID)
- my mistake, use [TKT456](ticketID)
- ohh, its [TKT456](ticketID)
- ok try [TKT456](ticketID)

## intent:get_ticket_status
- What is the current status of my ticket [TKT456](ticketID)
- get me the status of [TKT123](ticketID)
- show me the current status of [TKT456](ticketID)
- i need status of [TKT234](ticketID)
- gimme status of [TKT456](ticketID)
- find the status of [TKT678](ticketID)
- can you help me with the status of [TKT675](ticketID)
- get me status of [TKT555](ticketID)
- help me status of [TKT234](ticketID)
- track the status of [TKT789](ticketID)
- what is the progress on [TKT345](ticketID)
- report the progress of [TKT789](ticketID)
- gimme status of [TKT4566](ticketID)

## intent:file_upload_json
- [FPC96EY3V](file):[''](file_text)
- [FPC96EY3V](file):[Attachment](file_text)
- [FPC96EY3V](file):[Sample File](file_text)
- [FPC96EY3V](file):[Screenshot](file_text)
- [FPC96EY3V](file):[""](file_text)
- [FPC96EY3V](file):[file for analysis](file_text)
- [FPC96EY3V](file):[test upload](file_text)
- [FPC96EY3V](file):[testing](file_text)
- [FPC96EY3V](file):[uploading for analysis](file_text)
- [FPC96EY3V](file):[PFA](file_text)
- [FPC96EY3V](file):[for debugging](file_text)
- [FPC96EY3V](file):[FYI](file_text)
- [FPC96EY3V](file):[for your reference](file_text)
- [FPC96EY3V](file):[check this](file_text)
- [FPC96EY3V](file):[error](file_text)
- [FPC96EY3V](file):[log file](file_text)
- [FPC96EY3V](file):[error log](file_text)
- [FPC96EY3V](file):[screenshots attached](file_text)
- [FPC96EY3V](file):[screenshot attached](file_text)
- [FPC96EY3V](file):[files attached](file_text)
- [FPC96EY3V](file):[file attached](file_text)
- [FPC96EY3V](file):[attached](file_text)
- [FPC96EY3V](file):[file uploaded](file_text)
- [FPC96EY3V](file):[view this](file_text)
- [FPC96EY3V](file):[have a look](file_text)
- [FPC96EY3V](file):[error files attached](file_text)
- [FPC96EY3V](file):[error file attached](file_text)
- [FPC96EY3V](file):[watever](file_text)
- [FPC96EY3V](file):[adding attachment](file_text)
- [FPC96EY3V](file):[testing attachment](file_text)
- [FPC96EY3V](file):[testing file upload](file_text)
- [FPC96EY3V](file):[attaching error loags](file_text)
- [FPC96EY3V](file):[attaching screenshots](file_text)
- [FPC96EY3V](file):[attaching document](file_text)
- [FPC96EY3V](file):[adding document](file_text)
- [FPC96EY3V](file):[adding doc](file_text)
- [FPC96EY3V](file):[uploading document](file_text)
- [FPC96EY3V](file):[uploding doc](file_text)
- [FPC96EY3V](file):[document added](file_text)
- [FPC96EY3V](file):[document attached](file_text)
- [FPC96EY3V](file):[doc file added](file_text)
- [FPC96EY3V](file):[docs](file_text)
- [FPC96EY3V](file):[doc](file_text)
- [FPC96EY3V](file):[doc attached](file_text)
- [FPC96EY3V](file):[file added](file_text)
- [FPC96EY3V](file):[have a look at the attached file](file_text)
- [FPC96EY3V](file):[file](file_text)
- [FPC96EY3V](file):[document](file_text)
- [FPC96EY3V](file):[doc](file_text)
- [FPC96EY3V](file):[log](file_text)
- [FPC96EY3V](file):[VPN](file_text)
- [FPC96EY3V](file):[VPN solution](file_text)
- [FPC96EY3V](file):[VPN log](file_text)
- [FPC96EY3V](file):[network connection log](file_text)
- [FPC96EY3V](file):[network connection error](file_text)
- [FPC96EY3V](file):[document for analysis](file_text)
- [FPC96EY3V](file):[attaching document for analysis](file_text)

## intent:small_talk
- What language are you written in
- Who are you?
- You are arrogant
- do you drink
- how much do you earn
- DO YOU PLAY SOCCER
- You are not immortal
- You do not make any sense
- You should be ashamed
- do you know gossip
- How is your health?
- Are you a programmer?
- Do you wish you could eat food?
- what is the stock market

## intent:thank
- Thanks, that was great help
- Thanks that was helpful
- That was indeed helpful
- thnx
- thank u
- thank you
- thanks
- Thank you
- Thanks
- Thank you so much
- Thanks bot
- Thanks for that
- cheers
- cheers bro
- ok thanks!
- perfect thank you
- thanks a ton
- thanks for the help
- thanks a lot
- amazing, thanks
- cool, thanks
- cool thank you
- thanks!
- thanks that was great help
- great, thanks

## intent:get_procurement_tickets
- get my pending tickets
- show procurement pending tickets
- get tickets awaiting my approval
- get tickets pending my approval
- All tasks waiting my approval

## intent:performance_feedback
- i would like to give some feedback for the bot
- i want to give feedback for bot
- can i give some feedback?
- can i say something regarding the bot performance?

## intent:user_feedback
- i [like](fdResponse) the performance of this bot
- i [like](fdResponse) the answers given by this bot
- i [like](fdResponse) this bot
- i [hate](fdResponse) this bot
- i [hate](fdResponse) this bot's performance

## regex:ticketID
- [azAz09]*

## regex:file
- [azAz09]*

## regex:file_text
- [azAz09\s+]*

## regex:priority
- [azAz\s+]*

## regex:file_upload_json
 - [azAz09]*:[azAz09\s+]*
 
## lookup:priority
 - high issues
 - med issues
 - low issues