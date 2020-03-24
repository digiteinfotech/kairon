import glob
import json
import logging
import os
import threading

import requests
import yaml
from quart import Quart, request, jsonify
from quart_cors import cors
from rasa.core.agent import Agent
from rasa.train import train_async

from bot_trainer.QuestionGeneration import QuestionGeneration
from bot_trainer.aqgFunction import AutomaticQuestionGenerator
from bot_trainer.history import ChatHistory
from bot_trainer.loading import load

loader = load()
app = Quart(__name__)
app = cors(app, allow_origin="*")
logging.basicConfig(level=logging.DEBUG)

system_properties = yaml.load(open('./system.yaml'), Loader=yaml.FullLoader)
aqg = AutomaticQuestionGenerator()
questionGeneration = QuestionGeneration()

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

history = ChatHistory(domain_path, os.getenv('mongo_url', system_properties['mongo_url']), os.getenv('mongo_db', system_properties['mongo_db']))

list_of_files1 = glob.glob(models_path+ "/*") # * means all if need specific format then *.csv
latest_file1 = max(list_of_files1, key=os.path.getctime)
modelpath = os.path.abspath(latest_file1)


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
async def para():
    global para_flag
    request_data = await request.data
    jsonObject = json.loads(request_data)
    paragraph = jsonObject['paragraph']
    task2 = threading.Thread(target=paraQ, args=(paragraph,))
    para_flag = 1
    task2.start()
    return jsonify({ "message": "Generating Questions"})





#predict intent service
@app.route("/predict", methods=['POST'])
async def predict():
    request_data = await request.data
    jsonObject = json.loads(request_data)
    query = jsonObject['query']
    Prediction = await agent.parse_message_using_nlu_interpreter(message_data=query, tracker=None)
    Prediction = Prediction["intent"]['name']
    qAndA = resolveQuesAndAnswer(Prediction)
    return jsonify({"intent": Prediction, "questions": qAndA.get("questions"), "answer": qAndA.get("answer")})



#remove intent service
@app.route("/removeintent" , methods=['POST'])
async def Rem1():
    global term, newdict, dictrand
    request_data = await request.data
    jsonObject = json.loads(request_data)
    intent_name = jsonObject['name_intent']


    if intent_name=='':
        return jsonify({'message': 'Please Enter Intent.'})
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

        finaldict = {'actions': list(newdict.keys()), "intents" : list(term.keys()), "responses": dictaction}

        with open(domain_path, 'w') as file:
            yaml.dump(finaldict, file)

        file_handler = open(stories_path,'w')
        for key2 in dictrand:
            file_handler.write('\n'+ "## " + "path_" + key2 )
            file_handler.write('\n'+ "* " + key2)
            file_handler.write('\n'+ "  - " + dictrand[key2])

            file_handler.write('\n')
        file_handler.close()

        return jsonify({"message": "intent removed"})
        
        
async def trainm():
    global agent, train_flag
    new_model = await train_async(domain= domain_path, config= config_path, training_files= train_path, force_training=False)
    logging.info("new model path :"+new_model)
    new_model_path = os.path.abspath(new_model)
    if new_model_path != modelpath:
        logging.info("loading model :" + new_model)
        agent = Agent.load(new_model_path)
    return {"message": "Model training done", "model": new_model_path}

    


#model training service
@app.route("/train" , methods=['GET'])
async def train_model():
    global train_flag
    #task = threading.Thread(target=trainm, args=())
    response = await trainm()
    #train_flag = 1
    #task.start()
    return jsonify(response)



#adding sentence to intent service
@app.route("/addComponent" , methods=['POST'])
async def Add():
    global term
    request_data = await request.data
    jsonObject = json.loads(request_data)
    intent_name = jsonObject['intentName']
    component = jsonObject['component']
    list3 = term[intent_name]

    if len(component) == 0 :

        return jsonify({"message": "select required fields"})

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

    
    return jsonify({'message' : 'Component added', "question": component})



#removing sentence from intent service
@app.route("/removeComponent" , methods=['POST'])
async def Rem():
    global term
    request_data = await request.data
    jsonObject = json.loads(request_data)
    component = jsonObject['component']
    intent_name = jsonObject['intentName']

    if len(component) == 0 :
        return jsonify({"message":"please enter required fields"})
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
            return jsonify({"message":"Component removed", "question": component})

        else:
            return jsonify({'message':'Sentence not present'})





#get intent list
@app.route("/getIntentList", methods=['GET'])
async def getIntentList():
    return json.dumps(list(term.keys()))

#getQuestions and Response for an intent
@app.route("/getQuestionsAndAnswer", methods=['POST'])
async def getQuestionsAndAnswer():
    request_data = await request.data
    jsonObject = json.loads(request_data)
    intentName = jsonObject['intentName']
    try:
        qAndA = resolveQuesAndAnswer(intentName)
    except:
        qAndA = []
    return jsonify(qAndA)

def resolveQuesAndAnswer(intentName):
    QuestionList = term[intentName]
    interm = "utter_" + intentName
    response = newdict.get(interm)
    if response == 'None':
        response = ""
    return {"questions": QuestionList, "answer": response}
    
# Add answer
@app.route("/addAnswer" , methods=['POST'])
async def addAnswer():
    global newdict,dictrand
    request_data = await request.data
    jsonObject = json.loads(request_data)
    intent_name = jsonObject['intentName']
    action = "utter_" + intent_name
    answer = jsonObject['answer']
    
    newdict[action] = answer
    dictrand[intent_name] = action
    
    dictaction = dict()
    for k, v in newdict.items():
        dictaction[k] = [{"text": v}]
    
    finaldict = {'actions': list(newdict.keys()), "intents": list(term.keys()), "responses": dictaction}
    
    with open(domain_path, 'w') as file:
        yaml.dump(finaldict, file)
    
    file_handler = open(stories_path,'w')
    for key2 in dictrand:
        file_handler.write('\n'+ "## " + "path_" + key2 )
        file_handler.write('\n'+ "* " + key2)
        file_handler.write('\n'+ "  - " + dictrand[key2])

        file_handler.write('\n')
    file_handler.close()
    
    return jsonify({'message' : 'Response added', "answer": answer})
    
    
#add intent

@app.route("/newintent", methods=['POST'])
async def newintent():
    global term, newdict, dictrand
    request_data = await request.data
    jsonObject = json.loads(request_data)
    intent_name = jsonObject['intentName']

        
    if intent_name == 'default' or intent_name in list(term.keys()) or "intent" in intent_name:

        return jsonify({"message": "Intent Name Not Accepted"})
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

        finaldict = {'actions': list(newdict.keys()), "intents" : list(term.keys()), "responses": dictaction}

        with open(domain_path, 'w') as file:
            yaml.dump(finaldict, file)

        file_handler = open(stories_path,'w')
        for key2 in dictrand:
            file_handler.write('\n'+ "## " + "path_" + key2 )
            file_handler.write('\n'+ "* " + key2)
            file_handler.write('\n'+ "  - " + dictrand[key2])

            file_handler.write('\n')
        file_handler.close()

        return jsonify({"message": "Intent Added", "intent": intent_name})

'''
def variate1(List):
    global variation_flag
    variation = genquest.comb(List)
    variation_flag = 0
    return { "message": "Variations generated", "variations" : variation}
'''
    
#generate variations [accept string(s) in list format]
@app.route("/variations", methods=['POST'])
async def variations():
    global variation_flag
    request_data = await request.data
    jsonObject = json.loads(request_data)
    question_list: list = jsonObject['questionList']
    #task1 = threading.Thread(target=variate1, args=(QuestionList, ))
    #variation_flag = 1
    #task1.start()
    #new_questions= variate1(QuestionList)
    if question_list.__len__() <=5:
        result = await questionGeneration.generateQuestions(question_list)
        message = "Variations generated"
    else:
        message = "Sorry!, Max 5 questions can be selected for generation"
        result = None
    return jsonify({ "message": message, "variations" : result})

@app.route("/history/users", methods=['GET'])
async def chat_history_users():
    return jsonify(history.fetch_chat_users())


@app.route("/history/users/<sender>", methods=['POST'])
async def chat_history(sender):
    return jsonify(list(history.fetch_chat_history(sender)))
    
#chat intent service
@app.route("/chat", methods=['POST'])
async def chat():
    request_data = await request.data
    jsonObject = json.loads(request_data)
    query = jsonObject['query']
    bot_response = await agent.handle_text(text_message=query)
    return jsonify({"message": bot_response[0]['text']})
    
    

#add Generated variations to the existing list of questions for an intent
@app.route("/storeVariations", methods=['POST'])
async def storeVariations():
    global term
    request_data = await request.data
    jsonObject = json.loads(request_data)
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
    
    
    return jsonify({ "message": "Variations Stored", "questions": QuestionList})
    
    
# get status of flags
@app.route("/getAppStatus", methods=['GET'])
async def getFlags():
    return jsonify({"variation": variation_flag, "model":  train_flag, "paragraph": para_flag})
    
#deploy code
@app.route("/deploy" , methods=['POST'])
async def deploy():
    list_of_files = glob.glob(models_path + '/*')
    latest_file = max(list_of_files, key=os.path.getctime)
    model_path = os.path.abspath(latest_file)
    
    url = os.getenv("chatbot_url",system_properties["chatbot_url"])
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    req= {
     "model_file": model_path
    }
    requests.put(url, json = req,headers=headers)
    return jsonify({"message":"Deploying model"})
