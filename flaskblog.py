#import libraries
import requests
import threading
from flask import Flask, request
from flask_cors import CORS
from flask import jsonify
import json
import os
import glob
import yaml
import asyncio
from rasa.core.agent import Agent
from rasa import train
import nest_asyncio
from rasa.core.tracker_store import MongoTrackerStore
from rasa.core.domain import Domain
from .questionVariations import Variate
from .aqgFunction import AutomaticQuestionGenerator
from .loading import load
loader = load()
aqg = AutomaticQuestionGenerator()
genquest = Variate()

nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

variation_flag = 0
train_flag = 0
para_flag = 0



#establishing  paths of the rasa bot files
original_path = '.'
nlu_path = original_path + "/data/nlu.md"
stories_path = original_path + "/data/stories.md"
models_path = original_path  + "/models"
domain_path = original_path +  "/domain.yml"
config_path = original_path +  "/config.yml"
train_path =  original_path + "/data/"

domain = Domain.load(domain_path)
db = MongoTrackerStore(domain=domain,host="mongodb://192.168.101.148:27019", db="conversation")

list_of_files1 = glob.glob(models_path+ "/*") # * means all if need specific format then *.csv
latest_file1 = max(list_of_files1, key=os.path.getctime)
modelpath = os.path.abspath(latest_file1)
system_properties = yaml.load(open('./system.yaml'), Loader=yaml.FullLoader)

agent = Agent.load(modelpath)

term = loader.load_intent(nlu_path)
newdict = loader.load_domain(domain_path)
dictrand = loader.load_story(stories_path,term,newdict)


def paraQ(paragraph):
    global para_flag
    questionList = aqg.aqgParse(paragraph)
    FinalList = aqg.display(questionList)
    para_flag = 0
    return {"message": "Questions Generated" , "Questions" : FinalList}



#service for question generation from paragraph            
@app.route("/para", methods=['POST'])
def para():
    global para_flag
    jsonObject = json.loads(request.data)
    paragraph = jsonObject['paragraph']
    task2 = threading.Thread(target=paraQ, args=(paragraph,))
    para_flag = 1
    task2.start()
    return { "message": "Generating Questions"}





#predict intent service
@app.route("/predict", methods=['POST'])
def predict():
    jsonObject = json.loads(request.data)
    query = jsonObject['query']
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    Prediction = asyncio.run(agent.parse_message_using_nlu_interpreter(message_data=query, tracker=None))
    Prediction = Prediction["intent"]['name']
    qAndA = resolveQuesAndAnswer(Prediction)
    return {"intent": Prediction, "questions": qAndA.get("questions"), "answer": qAndA.get("answer")}



#remove intent service
@app.route("/removeintent" , methods=['POST'])
def Rem1():
    global term, newdict, dictrand
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['name_intent']


    if intent_name=='':
        return {'message': 'Please Enter Intent.'}
    else:
        req1 = intent_name
        req2 = "utter_" + req1
        del term[req1]
        del newdict[req2]
        del dictrand[req1]

        file_handler = open(nlu_path,'w')
        for finalkeys in list(term.keys()):

            file_handler.write('\n'+ "## intent:")
            file_handler.write(finalkeys)

            for value in term[finalkeys]:

                file_handler.write('\n'+ "- " + value)

            file_handler.write('\n')
        file_handler.close()

        dictaction= dict()
        for k,v in newdict.items():
            dictaction[k] = [{"text" : v}]

        finaldict = {'actions': list(newdict.keys()), "intents" : list(term.keys()), "templates": dictaction}

        with open(domain_path, 'w') as file:
            yaml.dump(finaldict, file)

        file_handler = open(stories_path,'w')
        for key2 in dictrand:
            file_handler.write('\n'+ "## " + "path_" + key2 )
            file_handler.write('\n'+ "* " + key2)
            file_handler.write('\n'+ "  - " + dictrand[key2])

            file_handler.write('\n')
        file_handler.close()

        return {"message": "intent removed"}
        
        
def trainm():
    global agent, train_flag
    #os.chdir(original_path)
    asyncio.set_event_loop(asyncio.new_event_loop())
    train(domain= domain_path, config= config_path, training_files= train_path, force_training=False)

    list_of_files = glob.glob(models_path + '/*')
    latest_file = max(list_of_files, key=os.path.getctime)
    modelpath1 = os.path.abspath(latest_file)

    agent = Agent.load(modelpath1)
    train_flag = 0

    return {"message": "Model training done"}

    


#model training service
@app.route("/train" , methods=['GET'])
def train_model():
    global train_flag
    task = threading.Thread(target=trainm, args=())
    train_flag = 1
    task.start()
    return {"message": "model training started"}



#adding sentence to intent service
@app.route("/addComponent" , methods=['POST'])
def Add():
    global term
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['intentName']
    component = jsonObject['component']
    list3 = term[intent_name]

    if len(component) == 0 :

        return {"message": "select required fields"}

    list3.append(component)

    tup = list3
    term[intent_name] = tup
    file_handler = open(nlu_path,'w')
    for finalkeys in list(term.keys()):

        file_handler.write('\n'+ "## intent:")
        file_handler.write(finalkeys)

        for value in term[finalkeys]:

            file_handler.write('\n'+ "- " + value)

        file_handler.write('\n')
    file_handler.close()

    
    return {'message' : 'Component added', "question": component}



#removing sentence from intent service
@app.route("/removeComponent" , methods=['POST'])
def Rem():
    global term
    jsonObject = json.loads(request.data)
    component = jsonObject['component']
    intent_name = jsonObject['intentName']


    if len(component) == 0 :

        return {"message":"please enter required fields"}
    else:

        pick8 = term[intent_name]
        if component in pick8:
            pick8.remove(component)
            term[intent_name] = pick8

            file_handler = open(nlu_path,'w')
            for finalkeys in list(term.keys()):

                file_handler.write('\n'+ "## intent:")
                file_handler.write(finalkeys)

                for value in term[finalkeys]:

                    file_handler.write('\n'+ "- " + value)

                file_handler.write('\n')
            file_handler.close()
            return {"message":"Component removed", "question": component}

        else:
            return {'message':'Sentence not present'}





#get intent list
@app.route("/getIntentList", methods=['GET'])
def getIntentList():
    return json.dumps(list(term.keys()))

#getQuestions and Response for an intent
@app.route("/getQuestionsAndAnswer", methods=['POST'])
def getQuestionsAndAnswer():
    jsonObject = json.loads(request.data)
    intentName = jsonObject['intentName']
    qAndA = resolveQuesAndAnswer(intentName)

    return qAndA

def resolveQuesAndAnswer(intentName):
    QuestionList = term[intentName]
    interm = "utter_" + intentName
    response = newdict.get(interm)
    if response == 'None':
        response = ""
    return dict({"questions": QuestionList, "answer": response})
    
# Add answer
@app.route("/addAnswer" , methods=['POST'])
def addAnswer():
    global newdict,dictrand
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['intentName']
    action = "utter_" + intent_name
    answer = jsonObject['answer']
    
    newdict[action] = answer
    dictrand[intent_name] = action
    
    dictaction = dict()
    for k, v in newdict.items():
        dictaction[k] = [{"text": v}]
    
    finaldict = {'actions': list(newdict.keys()), "intents": list(term.keys()), "templates": dictaction}
    
    with open(domain_path, 'w') as file:
        yaml.dump(finaldict, file)
    
    file_handler = open(stories_path,'w')
    for key2 in dictrand:
        file_handler.write('\n'+ "## " + "path_" + key2 )
        file_handler.write('\n'+ "* " + key2)
        file_handler.write('\n'+ "  - " + dictrand[key2])

        file_handler.write('\n')
    file_handler.close()
    
    return {'message' : 'Response added', "answer": answer}
    
    
#add intent

@app.route("/newintent", methods=['POST'])
def newintent():
    global term, newdict, dictrand
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['intentName']

        
    if intent_name == 'default' or intent_name in list(term.keys()) or "intent" in intent_name:

        return {"message": "Intent Name Not Accepted"}
    else:

        intent = intent_name
        response = ""
        action = "utter_"+intent
        Questions = []

        term[intent] = Questions
        newdict[action] = response
        dictrand[intent] = action

        file_handler = open(nlu_path,'w')
        for finalkeys in list(term.keys()):

            file_handler.write('\n'+ "## intent:")
            file_handler.write(finalkeys)

            for value in term[finalkeys]:

                file_handler.write('\n'+ "- " + value)

            file_handler.write('\n')
        file_handler.close()

        dictaction= dict()
        for k,v in newdict.items():
            dictaction[k] = [{"text" : v}]

        finaldict = {'actions': list(newdict.keys()), "intents" : list(term.keys()), "templates": dictaction}

        with open(domain_path, 'w') as file:
            yaml.dump(finaldict, file)

        file_handler = open(stories_path,'w')
        for key2 in dictrand:
            file_handler.write('\n'+ "## " + "path_" + key2 )
            file_handler.write('\n'+ "* " + key2)
            file_handler.write('\n'+ "  - " + dictrand[key2])

            file_handler.write('\n')
        file_handler.close()

        return {"message": "Intent Added", "intent": intent_name}


def variate1(List):
    global variation_flag
    variation = genquest.comb(List)
    variation_flag = 0
    return { "message": "Variations generated", "variations" : variation}    

    
#generate variations [accept string(s) in list format]
@app.route("/variations", methods=['POST'])
def variations():
    global variation_flag
    jsonObject = json.loads(request.data)
    QuestionList = jsonObject['questionList']
    task1 = threading.Thread(target=variate1, args=(QuestionList, ))
    variation_flag = 1
    task1.start()
    
    return { "message": "Generating Variations"}



@app.route("/history/users", methods=['GET'])
def chat_history_users():
    return jsonify(db.keys())


@app.route("/history/users/<sender>", methods=['POST'])
def chat_history(sender):
    return jsonify(list(fetch_chat_history(sender)))

def fetch_chat_history(sender):
    events = db.retrieve(sender).as_dialogue().events
    for event in events:
        event_data = event.as_dict()
        if event_data['event'] in ['user', 'bot']:
            yield {'event': event_data['event'],'text':event_data['text']}
    
#chat intent service
@app.route("/chat", methods=['POST'])
def chat():
    jsonObject = json.loads(request.data)
    query = jsonObject['query']
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    Prediction = asyncio.run(agent.parse_message_using_nlu_interpreter(message_data=query, tracker=None))
    Prediction = Prediction["intent"]['name']
    qAndA = resolveQuesAndAnswer(Prediction)
    answer = qAndA.get("answer")
    if answer == '':
        answer = newdict.get("utter_default")
    return {"message": answer}
    
    

#add Generated variations to the existing list of questions for an intent
@app.route("/storeVariations", methods=['POST'])
def storeVariations():
    global term
    jsonObject = json.loads(request.data)
    intentName = jsonObject['intentName']
    QuestionList = jsonObject['questionList']
    term[intentName] = term[intentName] + QuestionList
    file_handler = open(nlu_path,'w')
    for finalkeys in list(term.keys()):

        file_handler.write('\n'+ "## intent:")
        file_handler.write(finalkeys)

        for value in term[finalkeys]:

            file_handler.write('\n'+ "- " + value)

        file_handler.write('\n')
    file_handler.close()
    
    
    return { "message": "Variations Stored", "questions": QuestionList}
    
    
# get status of flags
@app.route("/getAppStatus", methods=['GET'])
def getFlags():
    return {"variation": variation_flag, "model":  train_flag, "paragraph": para_flag}
    
#deploy code
@app.route("/deploy" , methods=['POST'])
def deploy():
    list_of_files = glob.glob(models_path + '/*')
    latest_file = max(list_of_files, key=os.path.getctime)
    model_path = os.path.abspath(latest_file)
    
    url = system_properties["chatbot_url"]
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    req0= {
     "model_file": model_path,
     "model_server": {
       "url": url,
       "params": {},
       "headers": {},
       "basic_auth": {},
       "wait_time_between_pulls": 0
         }
    }
    requests.put(url, data = json.dumps(req0),headers=headers)
    
    

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
