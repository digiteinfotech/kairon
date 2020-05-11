<a name=".api_auth"></a>
## api\_auth

<a name=".api_auth.Authentication"></a>
### Authentication

```python
class Authentication()
```

This class defines functions that are necessary for the authentication processes of
the bot trainer

<a name=".api_auth.Authentication.get_current_user"></a>
#### get\_current\_user

```python
 | async get_current_user(request: Request, token: str = Depends(Utility.oauth2_scheme))
```

Validates the user credentials and facilitates the login process

<a name=".api_auth.Authentication.authenticate"></a>
#### authenticate

```python
 | authenticate(username: Text, password: Text)
```

Generates an access token if the user name and password match

<a name=".api_auth.Authentication.generate_integration_token"></a>
#### generate\_integration\_token

```python
 | generate_integration_token(bot: Text, account: int)
```

Generates an access token for secure integration of the bot
with an external service/architecture

<a name=".api_processor"></a>
## api\_processor

<a name=".api_processor.AccountProcessor.add_account"></a>
#### add\_account

```python
 | @staticmethod
 | add_account(name: str, user: str)
```

Adds a new account for the trainer app

<a name=".api_processor.AccountProcessor.get_account"></a>
#### get\_account

```python
 | @staticmethod
 | get_account(account: int)
```

Returns an account object based on user ID

<a name=".api_processor.AccountProcessor.add_bot"></a>
#### add\_bot

```python
 | @staticmethod
 | add_bot(name: str, account: int, user: str)
```

Adds a bot to the specified user account

<a name=".api_processor.AccountProcessor.get_bot"></a>
#### get\_bot

```python
 | @staticmethod
 | get_bot(id: str)
```

Loads the bot based on user ID

<a name=".api_processor.AccountProcessor.add_user"></a>
#### add\_user

```python
 | @staticmethod
 | add_user(email: str, password: str, first_name: str, last_name: str, account: int, bot: str, user: str, is_integration_user=False, role="trainer")
```

Adds a new user to the app based on the details
provided by the user

<a name=".api_processor.AccountProcessor.get_user"></a>
#### get\_user

```python
 | @staticmethod
 | get_user(email: str)
```

Returns the user object based on input email

<a name=".api_processor.AccountProcessor.get_user_details"></a>
#### get\_user\_details

```python
 | @staticmethod
 | get_user_details(email: str)
```

Get details of the user such as account name and the
chatbot he/she is training based on email input

<a name=".api_processor.AccountProcessor.get_complete_user_details"></a>
#### get\_complete\_user\_details

```python
 | @staticmethod
 | get_complete_user_details(email: str)
```

Get details of the user such as the account name, user ID,
and the chatbot he/she is training based on email input

<a name=".api_processor.AccountProcessor.get_integration_user"></a>
#### get\_integration\_user

```python
 | @staticmethod
 | get_integration_user(bot: str, account: int)
```

Getting the integration user. If it does'nt exist, a new integration user
is created

<a name=".api_processor.AccountProcessor.account_setup"></a>
#### account\_setup

```python
 | @staticmethod
 | account_setup(account_setup: Dict, user: Text)
```

Creating a new account based on details provided by the user

<a name=".api_processor.AccountProcessor.default_account_setup"></a>
#### default\_account\_setup

```python
 | @staticmethod
 | default_account_setup()
```

Setting up an account for testing/demo purposes

<a name=".augment"></a>
## augment

<a name=".augment.questions"></a>
#### questions

```python
@router.post("/questions", response_model=Response)
async questions(request_data: ListData, current_user: User = Depends(auth.get_current_user))
```

This function returns the augmentation url present in the system.yaml file

<a name=".auth"></a>
## auth

<a name=".auth.login_for_access_token"></a>
#### login\_for\_access\_token

```python
@router.post("/login", response_model=Response)
async login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends())
```

This function accepts the Request Form data and generates an access token only if
the user name and password are authenticated

<a name=".auth.generate_integration_token"></a>
#### generate\_integration\_token

```python
@router.get("/integration/token", response_model=Response)
async generate_integration_token(current_user: User = Depends(auth.get_current_user))
```

This function generates an access token to integrate the bot
with other external services/architectures

<a name=".bot"></a>
## bot

<a name=".bot.get_intents"></a>
#### get\_intents

```python
@router.get("/intents", response_model=Response)
async get_intents(current_user: User = Depends(auth.get_current_user))
```

This function returns the list of existing intents of the bot

<a name=".bot.add_intents"></a>
#### add\_intents

```python
@router.post("/intents", response_model=Response)
async add_intents(request_data: TextData, current_user: User = Depends(auth.get_current_user))
```

This function is used to add a new intent to the bot

<a name=".bot.predict_intent"></a>
#### predict\_intent

```python
@router.post("/intents/predict", response_model=Response)
async predict_intent(request_data: TextData, current_user: User = Depends(auth.get_current_user))
```

This function returns the predicted intent of the entered text by using the trained
rasa model of the chatbot

<a name=".bot.get_training_examples"></a>
#### get\_training\_examples

```python
@router.get("/training_examples/{intent}", response_model=Response)
async get_training_examples(intent: str, current_user: User = Depends(auth.get_current_user))
```

This function is used to return the training examples (questions/sentences)
which are used to train the chatbot, for a particular intent

<a name=".bot.add_training_examples"></a>
#### add\_training\_examples

```python
@router.post("/training_examples/{intent}", response_model=Response)
async add_training_examples(intent: str, request_data: ListData, current_user: User = Depends(auth.get_current_user))
```

This is used to add a new training example (sentence/question) for a
particular intent

<a name=".bot.remove_training_examples"></a>
#### remove\_training\_examples

```python
@router.delete("/training_examples", response_model=Response)
async remove_training_examples(request_data: TextData, current_user: User = Depends(auth.get_current_user))
```

This function is used to delete a particular training example (question/sentence) from a list
of examples for a particular intent

<a name=".bot.get_responses"></a>
#### get\_responses

```python
@router.get("/response/{utterance}", response_model=Response)
async get_responses(utterance: str, current_user: User = Depends(auth.get_current_user))
```

This function returns the list of responses for a particular utterance of the bot

<a name=".bot.add_responses"></a>
#### add\_responses

```python
@router.post("/response/{utterance}", response_model=Response)
async add_responses(request_data: TextData, utterance: str, current_user: User = Depends(auth.get_current_user))
```

This function adds a response to the list of responses for a particular utterance
of the bot

<a name=".bot.remove_responses"></a>
#### remove\_responses

```python
@router.delete("/response", response_model=Response)
async remove_responses(request_data: TextData, current_user: User = Depends(auth.get_current_user))
```

This function removes the bot response from the response list for a particular
utterance

<a name=".bot.add_stories"></a>
#### add\_stories

```python
@router.post("/stories", response_model=Response)
async add_stories(story: StoryRequest, current_user: User = Depends(auth.get_current_user))
```

This function is used to add a story (conversational flow) to the chatbot

<a name=".bot.get_stories"></a>
#### get\_stories

```python
@router.get("/stories", response_model=Response)
async get_stories(current_user: User = Depends(auth.get_current_user))
```

This returns the existing list of stories (conversation flows) of the bot

<a name=".bot.get_story_from_intent"></a>
#### get\_story\_from\_intent

```python
@router.get("/utterance_from_intent/{intent}", response_model=Response)
async get_story_from_intent(intent: str, current_user: User = Depends(auth.get_current_user))
```

This function returns the utterance or response that is mapped to a particular intent

<a name=".bot.chat"></a>
#### chat

```python
@router.post("/chat", response_model=Response)
async chat(request_data: TextData, current_user: User = Depends(auth.get_current_user))
```

This function returns a bot response for a given text/query. It is basically
used to test the chat functionality of the bot

<a name=".bot.train"></a>
#### train

```python
@router.post("/train", response_model=Response)
async train(current_user: User = Depends(auth.get_current_user))
```

This is used to train the chatbot

<a name=".bot.deploy"></a>
#### deploy

```python
@router.post("/deploy", response_model=Response)
async deploy(current_user: User = Depends(auth.get_current_user))
```

This function is used to deploy the model of the currently trained chatbot

<a name=".cloud_loader"></a>
## cloud\_loader

<a name=".cloud_loader.FileUploader.upload_File"></a>
#### upload\_File

```python
 | @staticmethod
 | upload_File(file, bucket)
```

Uploads the selected file to a specific bucket in Amazon Simple Storage Service

<a name=".generator"></a>
## generator

<a name=".generator.QuestionGenerator"></a>
### QuestionGenerator

```python
class QuestionGenerator()
```

This class defines the functions and models required to generate variations
for a given sentence/question

<a name=".generator.QuestionGenerator.get_synonyms_from_embedding"></a>
#### get\_synonyms\_from\_embedding

```python
 | @staticmethod
 | get_synonyms_from_embedding(text: str)
```

This function uses the google word2vec model to generate synonyms
for a given word

<a name=".generator.QuestionGenerator.checkDistance"></a>
#### checkDistance

```python
 | @staticmethod
 | checkDistance(source, target)
```

This function checks how contextually similar two sentences/questions are
and returns a value between 0 and 1 (0 being the least similar and 1 being the most)

<a name=".generator.QuestionGenerator.generateQuestions"></a>
#### generateQuestions

```python
 | @staticmethod
 | async generateQuestions(texts)
```

This function generates a list of variations for a given sentence/question.
E.g. QuestionGenerator.generateQuestions('your question') will return the list
of variations for that particular question

<a name=".history"></a>
## history

<a name=".history.ChatHistory.get_tracker_and_domain"></a>
#### get\_tracker\_and\_domain

```python
 | @staticmethod
 | get_tracker_and_domain(bot: Text)
```

Returns the Mongo Tracker and Domain of the bot

<a name=".history.ChatHistory.fetch_chat_history"></a>
#### fetch\_chat\_history

```python
 | @staticmethod
 | fetch_chat_history(bot: Text, sender, latest_history=False)
```

Returns the chat history of the user with the specified bot

<a name=".history.ChatHistory.fetch_chat_users"></a>
#### fetch\_chat\_users

```python
 | @staticmethod
 | fetch_chat_users(bot: Text)
```

Returns the chat user list of the specified bot

<a name=".history.ChatHistory.fetch_user_history"></a>
#### fetch\_user\_history

```python
 | @staticmethod
 | fetch_user_history(bot: Text, sender_id: Text, latest_history=True)
```

Returns the chat history of the bot with a particular user

<a name=".history.ChatHistory.visitor_hit_fallback"></a>
#### visitor\_hit\_fallback

```python
 | @staticmethod
 | visitor_hit_fallback(bot: Text)
```

Counts the number of times, the bot was unable to provide a response
to users

<a name=".history.ChatHistory.conversation_steps"></a>
#### conversation\_steps

```python
 | @staticmethod
 | conversation_steps(bot: Text)
```

Returns the number of conversation steps of the chat between the bot and its users

<a name=".history.ChatHistory.conversation_time"></a>
#### conversation\_time

```python
 | @staticmethod
 | conversation_time(bot: Text)
```

Returns the duration of the chat between a bot and its users

<a name=".history.ChatHistory.get_conversations"></a>
#### get\_conversations

```python
 | @staticmethod
 | get_conversations(bot: Text)
```

Returns all the conversations of a bot with its users

<a name=".importer"></a>
## importer

<a name=".importer.MongoDataImporter"></a>
### MongoDataImporter

```python
class MongoDataImporter(TrainingDataImporter):
 |  MongoDataImporter(bot: str)
```

This class defines the functions that are used to load data
from the bot files

<a name=".importer.MongoDataImporter.get_nlu_data"></a>
#### get\_nlu\_data

```python
 | async get_nlu_data(language: Optional[Text] = "en") -> TrainingData
```

Loads the data from the nlu file of the bot

<a name=".importer.MongoDataImporter.get_domain"></a>
#### get\_domain

```python
 | async get_domain() -> Domain
```

loads the data from the domain file of the bot

<a name=".importer.MongoDataImporter.get_config"></a>
#### get\_config

```python
 | async get_config() -> Dict
```

loads the data from the config file of the bot

<a name=".importer.MongoDataImporter.get_stories"></a>
#### get\_stories

```python
 | async get_stories(interpreter: "NaturalLanguageInterpreter" = RegexInterpreter(), template_variables: Optional[Dict] = None, use_e2e: bool = False, exclusion_percentage: Optional[int] = None) -> StoryGraph
```

Loads the data from the stories file of the bot

<a name=".main"></a>
## main

<a name=".main.startup"></a>
#### startup

```python
@app.on_event("startup")
async startup()
```

MongoDB is connected on the bot trainer startup

<a name=".main.shutdown"></a>
#### shutdown

```python
@app.on_event("shutdown")
async shutdown()
```

MongoDB is disconnected when bot trainer is shut down

<a name=".main.startlette_exception_handler"></a>
#### startlette\_exception\_handler

```python
@app.exception_handler(StarletteHTTPException)
async startlette_exception_handler(request, exc)
```

This function logs the Starlette HTTP error detected and returns the
appropriate message and details of the error

<a name=".main.http_exception_handler"></a>
#### http\_exception\_handler

```python
@app.exception_handler(HTTPException)
async http_exception_handler(request, exc)
```

This function logs the HTTP error detected and returns the
appropriate message and details of the error

<a name=".main.validation_exception_handler"></a>
#### validation\_exception\_handler

```python
@app.exception_handler(RequestValidationError)
async validation_exception_handler(request, exc)
```

logs the RequestValidationError detected and returns the
appropriate message and details of the error

<a name=".main.app_does_not_exist_exception_handler"></a>
#### app\_does\_not\_exist\_exception\_handler

```python
@app.exception_handler(DoesNotExist)
async app_does_not_exist_exception_handler(request, exc)
```

logs the DoesNotExist error detected and returns the
appropriate message and details of the error

<a name=".main.pymongo_exception_handler"></a>
#### pymongo\_exception\_handler

```python
@app.exception_handler(PyMongoError)
async pymongo_exception_handler(request, exc)
```

logs the PyMongoError detected and returns the
appropriate message and details of the error

<a name=".main.app_validation_exception_handler"></a>
#### app\_validation\_exception\_handler

```python
@app.exception_handler(ValidationError)
async app_validation_exception_handler(request, exc)
```

logs the ValidationError detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_operation_exception_handler"></a>
#### mongoengine\_operation\_exception\_handler

```python
@app.exception_handler(OperationError)
async mongoengine_operation_exception_handler(request, exc)
```

logs the OperationError detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_notregistered_exception_handler"></a>
#### mongoengine\_notregistered\_exception\_handler

```python
@app.exception_handler(NotRegistered)
async mongoengine_notregistered_exception_handler(request, exc)
```

logs the NotRegistered error detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_invalid_document_exception_handler"></a>
#### mongoengine\_invalid\_document\_exception\_handler

```python
@app.exception_handler(InvalidDocumentError)
async mongoengine_invalid_document_exception_handler(request, exc)
```

logs the InvalidDocumentError detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_lookup_exception_handler"></a>
#### mongoengine\_lookup\_exception\_handler

```python
@app.exception_handler(LookUpError)
async mongoengine_lookup_exception_handler(request, exc)
```

logs the LookUpError detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_multiple_objects_exception_handler"></a>
#### mongoengine\_multiple\_objects\_exception\_handler

```python
@app.exception_handler(MultipleObjectsReturned)
async mongoengine_multiple_objects_exception_handler(request, exc)
```

logs the MultipleObjectsReturned error detected and returns the
appropriate message and details of the error

<a name=".main.mongoengine_invalid_query_exception_handler"></a>
#### mongoengine\_invalid\_query\_exception\_handler

```python
@app.exception_handler(InvalidQueryError)
async mongoengine_invalid_query_exception_handler(request, exc)
```

logs the InvalidQueryError detected and returns the
appropriate message and details of the error

<a name=".main.app_exception_handler"></a>
#### app\_exception\_handler

```python
@app.exception_handler(AppException)
async app_exception_handler(request, exc)
```

logs the AppException error detected and returns the
appropriate message and details of the error

<a name=".processor"></a>
## processor

<a name=".processor.MongoProcessor.save_from_path"></a>
#### save\_from\_path

```python
 | save_from_path(path: Text, bot: Text, user="default")
```

This function reads the bot files, using the file path (input)
for a particular bot (input) and saves data into objects.
Eg. MongoProcessor.save_from_path(main_path,bot_name)

<a name=".processor.MongoProcessor.save_nlu"></a>
#### save\_nlu

```python
 | save_nlu(nlu: TrainingData, bot: Text, user: Text)
```

saves the nlu data (input) of the bot (input) into respective objects.
Eg. story_files, nlu_files = get_core_nlu_files(os.path.join(main_bot_path, DEFAULT_DATA_PATH))
    nlu = utils.training_data_from_paths(nlu_files, "en")
    MongoProcessor.save_nlu(nlu,bot_name,user_name)

<a name=".processor.MongoProcessor.load_nlu"></a>
#### load\_nlu

```python
 | load_nlu(bot: Text) -> TrainingData
```

loads nlu data of the bot (input) from respective objects.
Eg. MongoProcessor.load_nlu(bot_name)

<a name=".processor.MongoProcessor.save_domain"></a>
#### save\_domain

```python
 | save_domain(domain: Domain, bot: Text, user: Text)
```

saves the domain data (input) of the bot (input) into respective objects.
Eg. domain = Domain.from_file(os.path.join(main_path, DEFAULT_DOMAIN_PATH))
    MongoProcessor.save_domain(domain,bot_name,user_name)

<a name=".processor.MongoProcessor.load_domain"></a>
#### load\_domain

```python
 | load_domain(bot: Text) -> Domain
```

loads domain data of the bot (input) from respective objects.
Eg. MongoProcessor.load_domain(bot_name)

<a name=".processor.MongoProcessor.save_stories"></a>
#### save\_stories

```python
 | save_stories(story_steps: Text, bot: Text, user: Text)
```

saves the stories data (input) of the bot (input) into respective objects.
Eg. story_files, nlu_files = get_core_nlu_files(os.path.join(main_path, DEFAULT_DATA_PATH))
    domain = Domain.from_file(os.path.join(path, DEFAULT_DOMAIN_PATH))
    loop = asyncio.new_event_loop()
    story_steps = loop.run_until_complete(StoryFileReader.read_from_files(story_files, domain))
    MongoProcessor.save_stories(story_steps,bot_name,user_name)

<a name=".processor.MongoProcessor.load_stories"></a>
#### load\_stories

```python
 | load_stories(bot: Text) -> StoryGraph
```

loads the stories data of the bot (input) from the respective objects.
Eg. MongoProcessor.load_stories(bot_name)

<a name=".processor.MongoProcessor.fetch_synonyms"></a>
#### fetch\_synonyms

```python
 | fetch_synonyms(bot: Text, status=True)
```

Loads the entity synonyms of the bot (input).
Eg. MongoProcessor.fetch_synonyms(bot_name)

<a name=".processor.MongoProcessor.fetch_training_examples"></a>
#### fetch\_training\_examples

```python
 | fetch_training_examples(bot: Text, status=True)
```

Returns the training examples (questions/sentences) of the bot (input).
Eg. MongoProcessor.fetch_training_examples(bot_name)

<a name=".processor.MongoProcessor.fetch_lookup_tables"></a>
#### fetch\_lookup\_tables

```python
 | fetch_lookup_tables(bot: Text, status=True)
```

Returns the lookup tables of the bot (input).
Eg. MongoProcessor.fetch_lookup_tables(bot_name)

<a name=".processor.MongoProcessor.fetch_regex_features"></a>
#### fetch\_regex\_features

```python
 | fetch_regex_features(bot: Text, status=True)
```

Returns the regex features of the bot (input).
Eg. MongoProcessor.fetch_regex_features(bot_name)

<a name=".processor.MongoProcessor.fetch_intents"></a>
#### fetch\_intents

```python
 | fetch_intents(bot: Text, status=True)
```

Returns the intent list of the bot (input).
Eg. MongoProcessor.fetch_intents(bot_name)

<a name=".processor.MongoProcessor.fetch_domain_entities"></a>
#### fetch\_domain\_entities

```python
 | fetch_domain_entities(bot: Text, status=True)
```

Returns the list of entities of the bot (input).
Eg. MongoProcessor.fetch_domain_entities(bot_name)

<a name=".processor.MongoProcessor.fetch_forms"></a>
#### fetch\_forms

```python
 | fetch_forms(bot: Text, status=True)
```

Returns the list of forms of the bot (input).
Eg. MongoProcessor.fetch_forms(bot_name)

<a name=".processor.MongoProcessor.fetch_actions"></a>
#### fetch\_actions

```python
 | fetch_actions(bot: Text, status=True)
```

Returns the list of actions of the bot (input).
Eg. MongoProcessor.fetch_actions(bot_name)

<a name=".processor.MongoProcessor.fetch_session_config"></a>
#### fetch\_session\_config

```python
 | fetch_session_config(bot: Text)
```

Returns the session configurations of the bot (input).
Eg. MongoProcessor.fetch_session_config(bot_name)

<a name=".processor.MongoProcessor.fetch_responses"></a>
#### fetch\_responses

```python
 | fetch_responses(bot: Text, status=True)
```

Yields the response dictionary of the bot (input).
Eg. MongoProcessor.fetch_responses(bot_name)

<a name=".processor.MongoProcessor.fetch_slots"></a>
#### fetch\_slots

```python
 | fetch_slots(bot: Text, status=True)
```

Returns the list of slots of the bot (input).
Eg. MongoProcessor.fetch_slots(bot_name)

<a name=".processor.MongoProcessor.fetch_stories"></a>
#### fetch\_stories

```python
 | fetch_stories(bot: Text, status=True)
```

Returns the list of stories of the bot (input).
Eg. MongoProcessor.fetch_stories(bot_name)

<a name=".processor.MongoProcessor.fetch_configs"></a>
#### fetch\_configs

```python
 | fetch_configs(bot: Text)
```

Returns the configuration details of the bot (input).
Eg. MongoProcessor.fetch_configs(bot_name)

<a name=".processor.MongoProcessor.load_config"></a>
#### load\_config

```python
 | load_config(bot: Text)
```

Returns the configuration dictionary created from the config object of the bot (input).
Eg. MongoProcessor.load_config(bot_name)

<a name=".processor.MongoProcessor.add_intent"></a>
#### add\_intent

```python
 | add_intent(text: Text, bot: Text, user: Text)
```

Adds a new intent (input) to the bot (input).
Eg. MongoProcessor.add_intent(intent_name,bot_name,user_name)

<a name=".processor.MongoProcessor.get_intents"></a>
#### get\_intents

```python
 | get_intents(bot: Text)
```

Returns the list of intents of the bot (input)

<a name=".processor.MongoProcessor.add_training_example"></a>
#### add\_training\_example

```python
 | add_training_example(examples: List[Text], intent: Text, bot: Text, user: Text)
```

Adds a sentence/question (training example) for an intent of the bot.
Eg. MongoProcessor.add_training_example([training_example],intent_name,bot_name,user_name)

<a name=".processor.MongoProcessor.get_training_examples"></a>
#### get\_training\_examples

```python
 | get_training_examples(intent: Text, bot: Text)
```

Yields training examples for an intent of the bot.
Eg. MongoProcessor.get_training_examples(intent_name,bot_name)

<a name=".processor.MongoProcessor.get_all_training_examples"></a>
#### get\_all\_training\_examples

```python
 | get_all_training_examples(bot: Text)
```

Returns list of all training examples of a bot

<a name=".processor.MongoProcessor.remove_document"></a>
#### remove\_document

```python
 | remove_document(document: Document, id: Text, bot: Text, user: Text)
```

Removes a document of the bot.
Eg. MongoProcessor.remove_document(document_name,doc_ID,bot_name,user_name)

<a name=".processor.MongoProcessor.add_entity"></a>
#### add\_entity

```python
 | add_entity(name: Text, bot: Text, user: Text)
```

Adds an entity for a bot of a user.
Eg. MongoProcessor.add_entity(entity_name,bot_name,user_name)

<a name=".processor.MongoProcessor.get_entities"></a>
#### get\_entities

```python
 | get_entities(bot: Text)
```

Returns the list of entities of a bot (input)

<a name=".processor.MongoProcessor.add_action"></a>
#### add\_action

```python
 | add_action(name: Text, bot: Text, user: Text)
```

Adds an action to the bot.
Eg. MongoProcessor.add_action(action_name,bot_name,user_name)

<a name=".processor.MongoProcessor.get_actions"></a>
#### get\_actions

```python
 | get_actions(bot: Text)
```

Returns the list of actions of a bot (input)

<a name=".processor.MongoProcessor.add_text_response"></a>
#### add\_text\_response

```python
 | add_text_response(utterance: Text, name: Text, bot: Text, user: Text)
```

Adds a text response to an utterance of the bot.
Eg. MongoProcessor.add_text_response(response,utterance_name,bot_name,user_name)

<a name=".processor.MongoProcessor.add_response"></a>
#### add\_response

```python
 | add_response(utterances: Dict, name: Text, bot: Text, user: Text)
```

Adds an utterance to the bot.
Eg. MongoProcessor.add_response({utterance_dict},utterance_name,bot_name,user_name)

<a name=".processor.MongoProcessor.get_response"></a>
#### get\_response

```python
 | get_response(name: Text, bot: Text)
```

Yields bot response based on utterance name.
Eg. MongoProcessor.get_response(utterance_name,bot_name)

<a name=".processor.MongoProcessor.add_story"></a>
#### add\_story

```python
 | add_story(name: Text, events: List[Dict], bot: Text, user: Text)
```

Adds a new story to the bot.
Eg. MongoProcessor.add_story(story_name,[Dictionaries of conversation flow],bot_name,user_name)

<a name=".processor.MongoProcessor.get_stories"></a>
#### get\_stories

```python
 | get_stories(bot: Text)
```

Yields all the stories of the bot

<a name=".processor.MongoProcessor.get_utterance_from_intent"></a>
#### get\_utterance\_from\_intent

```python
 | get_utterance_from_intent(intent: Text, bot: Text)
```

Returns the bot response for a particular intent.
Eg. MongoProcessor.get_utterance_from_intent(intent_name,bot_name)

<a name=".processor.MongoProcessor.add_session_config"></a>
#### add\_session\_config

```python
 | add_session_config(bot: Text, user: Text, id: Text = None, sesssionExpirationTime: int = 60, carryOverSlots: bool = True)
```

Adds a session configuration to the bot.
Eg. MongoProcessor.add_session_config(bot_name,user_name)

<a name=".processor.MongoProcessor.get_session_config"></a>
#### get\_session\_config

```python
 | get_session_config(bot: Text)
```

Returns the session configuration of the bot (input)

<a name=".processor.MongoProcessor.add_endpoints"></a>
#### add\_endpoints

```python
 | add_endpoints(endpoint_config: Dict, bot: Text, user: Text)
```

Adds endpoints to the bot and user.
Eg. MongoProcessor.add_endpoints({endpoint config},bot_name,user_name)

<a name=".processor.MongoProcessor.get_endpoints"></a>
#### get\_endpoints

```python
 | get_endpoints(bot: Text, raise_exception=True)
```

Returns the endpoints of the bot (input)

<a name=".processor.AgentProcessor.get_agent"></a>
#### get\_agent

```python
 | @staticmethod
 | get_agent(bot: Text) -> Agent
```

Loads the agent of the bot (input)

<a name=".processor.AgentProcessor.reload"></a>
#### reload

```python
 | @staticmethod
 | reload(bot: Text)
```

Reloads the bot (input)

<a name=".routers_history"></a>
## routers\_history

<a name=".routers_history.chat_history_users"></a>
#### chat\_history\_users

```python
@router.get("/users", response_model=Response)
async chat_history_users(current_user: User = Depends(auth.get_current_user))
```

This function returns the list of the chatbot users

<a name=".routers_history.chat_history"></a>
#### chat\_history

```python
@router.get("/users/{sender}", response_model=Response)
async chat_history(sender: Text, current_user: User = Depends(auth.get_current_user))
```

This function returns the chat history for a particular user of the chatbot

<a name=".routers_history.visitor_hit_fallback"></a>
#### visitor\_hit\_fallback

```python
@router.get("/metrics/visitor_hit_fallback", response_model=Response)
async visitor_hit_fallback(current_user: User = Depends(auth.get_current_user))
```

This function returns the number of times the bot hit
a fallback (the bot admitting to not having a reply for a given
text/query) for a given user

<a name=".routers_history.conversation_steps"></a>
#### conversation\_steps

```python
@router.get("/metrics/conversation_steps", response_model=Response)
async conversation_steps(current_user: User = Depends(auth.get_current_user))
```

This function returns the number of conversation steps that took place in the chat
between the user and the chatbot

<a name=".routers_history.conversation_time"></a>
#### conversation\_time

```python
@router.get("/metrics/conversation_time", response_model=Response)
async conversation_time(current_user: User = Depends(auth.get_current_user))
```

This returns the duration of the chat that took place between the user and the
chatbot

<a name=".server"></a>
## server

<a name=".server.Response"></a>
### Response

```python
class Response(BaseModel)
```

This class defines the variables (and their types) that will be defined in the response
message when a HTTP error is detected

<a name=".server.startlette_exception_handler"></a>
#### startlette\_exception\_handler

```python
@app.exception_handler(StarletteHTTPException)
async startlette_exception_handler(request, exc)
```

This function logs the Starlette HTTP error detected and returns the
appropriate message and details of the error

<a name=".server.http_exception_handler"></a>
#### http\_exception\_handler

```python
@app.exception_handler(HTTPException)
async http_exception_handler(request, exc)
```

This function logs the HTTP error detected and returns the
appropriate message and details of the error

<a name=".server.chat"></a>
#### chat

```python
@app.post("/questions", response_model=Response)
async chat(request_data: List[Text])
```

This function returns the variations for a given list of sentences/questions

<a name=".train"></a>
## train

<a name=".train.train_model"></a>
#### train\_model

```python
async train_model(data_importer: TrainingDataImporter, output_path: Text, force_training: bool = False, fixed_model_name: Optional[Text] = None, persist_nlu_training_data: bool = False, additional_arguments: Optional[Dict] = None)
```

Trains the rasa model internally, using functions from the rasa modules

<a name=".train.train_model_from_mongo"></a>
#### train\_model\_from\_mongo

```python
async train_model_from_mongo(bot: str, force_training: bool = False, fixed_model_name: Optional[Text] = None, persist_nlu_training_data: bool = False, additional_arguments: Optional[Dict] = None)
```

Trains the rasa model, using the data that is loaded onto
Mongo, through the bot files

<a name=".user"></a>
## user

<a name=".user.chat_history_users"></a>
#### chat\_history\_users

```python
@router.get("/details", response_model=Response)
async chat_history_users(current_user: User = Depends(auth.get_current_user))
```

This function returns the details of the current user

<a name=".utils"></a>
## utils

<a name=".utils.Utility.check_empty_string"></a>
#### check\_empty\_string

```python
 | @staticmethod
 | check_empty_string(value: str)
```

Checks for an empty string. Returns True if empty or not a string,
and returns False if it is a string

<a name=".utils.Utility.prepare_nlu_text"></a>
#### prepare\_nlu\_text

```python
 | @staticmethod
 | prepare_nlu_text(example: Text, entities: List[Dict])
```

This function converts the entity data into the format required for the
nlu file of the bot

<a name=".utils.Utility.validate_document_list"></a>
#### validate\_document\_list

```python
 | @staticmethod
 | validate_document_list(documents: List[BaseDocument])
```

Returns the validation results (if the document schema is valid or not)
of the input documents

<a name=".utils.Utility.load_yaml"></a>
#### load\_yaml

```python
 | @staticmethod
 | load_yaml(file: Text)
```

Loads content from the .yaml file

<a name=".utils.Utility.load_evironment"></a>
#### load\_evironment

```python
 | @staticmethod
 | load_evironment()
```

Loads the environment variables and their values from the
system.yaml file for defining the working environment of the app

<a name=".utils.Utility.validate_fields"></a>
#### validate\_fields

```python
 | @staticmethod
 | validate_fields(fields: Dict, data: Dict)
```

Checks if the input fields of a dictionary
are valid (not empty) and returns an error if not

<a name=".utils.Utility.verify_password"></a>
#### verify\_password

```python
 | @staticmethod
 | verify_password(plain_password, hashed_password)
```

Verifies the password with the hashed version of the password

<a name=".utils.Utility.get_password_hash"></a>
#### get\_password\_hash

```python
 | @staticmethod
 | get_password_hash(password)
```

Returns the hashed version of the input password

<a name=".utils.Utility.get_latest_file"></a>
#### get\_latest\_file

```python
 | @staticmethod
 | get_latest_file(folder)
```

Gets the latest file in a folder

<a name=".utils.Utility.check_empty_list_elements"></a>
#### check\_empty\_list\_elements

```python
 | @staticmethod
 | check_empty_list_elements(items: List[Text])
```

Checks if the input strings are empty. Returns True if empty and False,
if not

<a name=".utils.Utility.deploy_model"></a>
#### deploy\_model

```python
 | @staticmethod
 | deploy_model(endpoint: Dict, bot: Text)
```

Deploys the chatbot to the specified endpoint

<a name=".utils.Utility.generate_password"></a>
#### generate\_password

```python
 | @staticmethod
 | generate_password(size=6, chars=string.ascii_uppercase + string.digits)
```

Generates a random password of 6 characters (letters and digits included)

