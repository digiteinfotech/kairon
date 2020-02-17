#import libraries
from flask import Flask, request
import json
from flair.data import Sentence
from flair.models import SequenceTagger
import nltk
from nltk.corpus import wordnet
from nltk import ngrams
from nltk.corpus import stopwords 
from nltk.stem import WordNetLemmatizer
import re
from autocorrect import Speller
import gensim
import os
import glob
import yaml
import asyncio
from rasa.core.agent import Agent
from rasa import train
import nest_asyncio
import sys
sys.path.append(os.getcwd())
import aqgFunction
aqg = aqgFunction.AutomaticQuestionGenerator()
nest_asyncio.apply()

lemmatizer = WordNetLemmatizer()

app = Flask(__name__)


#help verbs + stopword list
entity_helpverb_words = ['digite','agile','am', 'is', 'are','was', 'were', 'being', 'been', 'be','for','swiftly','in',
'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should','im','there','here','on','or','how','of',
                         'where','when','may', 'might', 'must', 'can', 'could','the','swiftalm', 'swift','kanban',
                         'alm','sap','cloud','scrum','jira','to','re','ve','mnc','wan','na','m','with','not']

pos = SequenceTagger.load('pos-fast')

#m = gensim.models.KeyedVectors.load_word2vec_format('wiki-news-300d-1M.vec')  #load model - this takes time


#Part of Speech function for wordnet lemmatizer
def get_wordnet_pos(word):
    """Map POS tag to first character lemmatize() accepts"""
    tag = nltk.pos_tag([word])[0][1][0].upper()
    tag_dict = {"J": wordnet.ADJ,
                "N": wordnet.NOUN,
                "V": wordnet.VERB,
                "R": wordnet.ADV}

    return tag_dict.get(tag, wordnet.NOUN)

#establishing  paths of the rasa bot files
global nlu_path, stories_path, models_path, domain_path, config_path, term, newdict, dictrand, train_path, agent
original_path = '.'
nlu_path = original_path + "/data/nlu.md"
stories_path = original_path + "/data/stories.md"
models_path = original_path  + "/models"
domain_path = original_path +  "/domain.yml"
config_path = original_path +  "/config.yml"
train_path =  original_path + "/data/"

list_of_files1 = glob.glob(models_path+ "/*") # * means all if need specific format then *.csv
latest_file1 = max(list_of_files1, key=os.path.getctime)
modelpath = os.path.abspath(latest_file1)

agent = Agent.load(modelpath)


# reading and creating dictionary from nlu.md file
with open(nlu_path, 'r') as f:
    text = f.readlines()
intent = None
sentences= []
term = dict()
for line in text:
    if "##" and ":" and "intent" in line:
        
        term[intent] = sentences
        sentences=[]
        intent = line.replace("##",'')
        intent = intent.replace("intent",'')
        intent = intent.replace(":",'')
        intent = intent.replace("\n",'')
        intent = intent.strip()


    else:
        line = line.replace("-",'')
        line = line.replace("\n",'')
        line = line.strip()
        sentences.append(line)
        if '' in sentences:
            sentences.remove('')
term[intent] = sentences
filtered = {k: v for k, v in term.items() if k is not None}
term.clear()
term.update(filtered)


#reading and creating dictionary from domain.yml file
with open(domain_path) as g:
    data1 = yaml.load(g, Loader=yaml.FullLoader)
data2 = data1["templates"]
newdict=dict()
for keys in data2:

    data3 = data2[keys]
    data4=data3[0]
    data5 = data4["text"]
    newdict[keys]= data5
    
dictrand={}
with open(stories_path, 'r') as h:
    text2 = h.readlines()
for line8 in text2:

    if "*" in line8:
        line9 = line8.replace("*","")
        line9= line9.strip()
        if line9 in list(term.keys()):
            first = line9
       ###### else : 
    if "##" not in line8 and "*" not in line8 and "-" in line8:
        line6 = line8.replace("-","")
        line6 = line6.strip()
        if line6 in list(newdict.keys()):
            second = line6
            dictrand[first]= second
            
#function to preprocess text            
def preprocess_text(text,lemmatizer,custom_stopwords,word_len,ngram_generation,shingle_generation,white_space=True,
                    lower_case=True,number=True,lemmatization = False,english_stopword=False):
    list_lemmatized_words = []
    filtered_tokens = []
    tokens = []
    stop_words =set()
    text = str(text)
   # removing white spaces from the both end of the text.
    if white_space == True:
        text = text.strip() 
    if lower_case == True:
        text = text.lower() # converting to the lower case.
    if number == True:
        text2 = re.sub('[^a-zA-Z]+',' ',str(text)) # Removing numbers from the text (for character shingle generation). 
        text = re.sub('[^a-zA-Z]+',' ',str(text)) # Removing numbers from the text.

    if shingle_generation != False:
        if "-" in shingle_generation:
            d =tuple(map(int,shingle_generation.split('-')))
            for i in range(d[0],d[1]+1):
                for j in range(len(text2)-(i+1)):
                    flag = 0
                    for xyz in range(len(custom_stopwords)):
                        if text2[j:j+i].lower().strip() in custom_stopwords[xyz]: # Removes the character shingle if it is substring of a custom stopword.
                            flag = 1
                            break
                    if flag == 0:
                        tokens.append(text2[j:j+i])
        else:
            d= tuple(map(int,shingle_generation.split(',')))
            for i in range(len(d)):
                for j in range(len(text2)-(d[i]+1)):
                    flag = 0
                    for xyz in range(len(custom_stopwords)):
                        if text2[j:j+d[i]].lower().strip() in custom_stopwords[xyz]: # Removes the character shingle if it is substring of a custom stopword.
                            flag = 1
                            break
                    if flag == 0:
                        tokens.append(text2[j:j+d[i]])

                
    if ngram_generation != False:
        if "-" in ngram_generation:
            e =tuple(map(int,ngram_generation.split('-')))
            for i in range(e[0],e[1]+1):
                NGrams = ngrams(text2.split(), i)
                new_list=[]
                for grams in NGrams:
                    new_list.append(' '.join(grams))
                tokens = tokens + new_list
                
        else:
            e= tuple(map(int,ngram_generation.split(',')))
            for i in range(len(e)):
                NGrams = ngrams(text2.split(), e[i])
                new_list=[]
                for grams in NGrams:
                    new_list.append(' '.join(grams))
                tokens = tokens + new_list
            
    if lemmatization == True:
        token1 = nltk.word_tokenize(text)
        for word in token1:
            list_lemmatized_words.append(lemmatizer.lemmatize(word)) # Lemmatizing each word.
    else:
        token1 = nltk.word_tokenize(text)
        for word in token1:
            list_lemmatized_words.append(word)
        
            
    if english_stopword == True:
        stop_words = set(stopwords.words('english')) # Reading english stopwords.

    filtered_tokens = [w for w in list_lemmatized_words if not w in stop_words and len(w)>word_len and not w in custom_stopwords] #1. Removing english stopwords, 2. Removing words present in custom stopwords list, 3. Removing words if length of the word is less than 4.
    final_tokens= filtered_tokens + tokens   
    return final_tokens
            
#function to generate variations of a given list of sentences (10 variations for each sentence)            
def comb(lis):
    
    word_dictionary = dict()
    for sent in lis:
        testr = preprocess_text(sent,WordNetLemmatizer(),entity_helpverb_words,0,ngram_generation=False,
                                shingle_generation=False,white_space=True,
                        lower_case=True,number=True,lemmatization = False,english_stopword=False)
        testf = preprocess_text(sent,WordNetLemmatizer(),[],0,ngram_generation=False,
                                shingle_generation=False,white_space=True,
                        lower_case=True,number=True,lemmatization = False,english_stopword=False)
        ace=' '.join(testr)
        f_pos=[]
        sentence = Sentence(ace)
        pos.predict(sentence)
            ## append tagged sentence ##
        f_pos.append(sentence.to_tagged_string())
        string1 = f_pos[0]
        postring=[]
        qwe=string1.split(" ")
        for i in range(len(qwe)):
            if qwe[i] == "<PRON>" or qwe[i] == "<DET>":
                postring.append(i)
        for position in postring:
            try:
                qwe[position] = " "
                qwe[position-1] = " "
            except:
                pass
        for word4 in qwe:
            if "<" in word4:
                qwe.remove(word4)                

        qwe = [i for i in qwe if i != " " and i not in entity_helpverb_words]
        for word1 in qwe:
            try:
                d= m.most_similar(word1,topn=35)
                listw=[]
                for asd in d:
                    listw.append(asd[0])
                list_middle = filt_func(listw)
                #####################################################################
                dag = lemmatizer.lemmatize(word1, get_wordnet_pos(word1))
                rd = []
                for ag in list_middle:
                    if lemmatizer.lemmatize(ag, get_wordnet_pos(ag)) != dag:
                        rd.append(ag)         
                #################################################################### 
                word_dictionary[word1]= rd
            except:
                pass
        collective=[]
        for i in range(10):
            listl = []
            for word in testf:
                try:
                    listab = word_dictionary[word]
                    listl.append(listab[i])
                except:
                    listl.append(word)
            collective.append(listl)

        collective2=[]
        for entity in collective:
            collective2.append(' '.join(entity))
    return collective2

#function to eliminate incorrect and similar words of the fast text model 
def filt_func(list1):
    spell = Speller(lang='en')
    list2=[]
    for word2 in list1:
        word3 = word2.strip()
        word4 = re.sub('[^a-zA-Z]+','',str(word3))
        word4 = word4.lower()
        word6 = spell(word4)
        list2.append(word6)
    list3=[]
    for word7 in list2:
        if word7 not in list3:
            list3.append(word7)
    list3 = list3[:21]
    return list3    


#predict intent service
@app.route("/predict", methods=['POST'])
def predict():
    jsonObject = json.loads(request.data)
    query = jsonObject['question']
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    Prediction = asyncio.run(agent.parse_message_using_nlu_interpreter(message_data=query, tracker=None))
    Prediction = Prediction["intent"]['name']
    
    return Prediction


#add intent service
@app.route("/newintent", methods=['POST'])
def newintent():
    global term, newdict, dictrand
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['name_intent']
    questions = jsonObject['ques']
    response = jsonObject['respond']
    
    if len(intent_name) == 0 or len(response) == 0:
        
        return {"message": "enter required fields"}
        
    elif len(questions)<5 :
        
        return {"message": "Number of Questions not sufficient"}
    
    else:
        
        if intent_name == 'default' or intent_name in list(term.keys()) or "intent" in intent_name:
            
            return {"message": "Intent Name Not Accepted"}
        else:
            
            intent = intent_name
            response = response
            action = "utter_"+intent
            Questions = questions
            
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
            
            return {"message": "Intent Added"}
        
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

        
#model training service        
@app.route("/train" , methods=['POST'])
def train_model():
    global agent
    #os.chdir(original_path)
    asyncio.set_event_loop(asyncio.new_event_loop())
    train(domain= domain_path, config= config_path, training_files= train_path, force_training=False)
    
    list_of_files = glob.glob(models_path + '/*') # * means all if need specific format then *.csv
    latest_file = max(list_of_files, key=os.path.getctime)
    modelpath1 = os.path.abspath(latest_file)
    
    agent = Agent.load(modelpath1)
    
    return {"message": "training done"}

#adding sentence to intent service
@app.route("/AddComponent" , methods=['POST'])
def Add():
    global term
    jsonObject = json.loads(request.data)
    intent_name = jsonObject['name_intent']
    component = jsonObject['comp']
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
    
    current = list()
    current.append(component)
    variate = comb(current)
    q1 = {'message' : 'Component added','variations': variate}
    
    return q1

#removing sentence from intent service
@app.route("/RemoveComponent" , methods=['POST'])
def Rem():
    global term
    jsonObject = json.loads(request.data)
    component1 = jsonObject['comp1']
    intent_name = jsonObject['name_intent']
    
    
    if len(component1) == 0 :
        
        return {"message":"please enter required fields"}
    else:
        
        pick8 = term[intent_name]
        if component1 in pick8:
            pick8.remove(component1)
            term[intent_name] = pick8
            
            file_handler = open(nlu_path,'w')
            for finalkeys in list(term.keys()):

                file_handler.write('\n'+ "## intent:")
                file_handler.write(finalkeys)

                for value in term[finalkeys]:

                    file_handler.write('\n'+ "- " + value)

                file_handler.write('\n')
            file_handler.close()
            return {"message":"Component removed"}
        
        else:
            return {'message':'Sentence not present'}
            
    

#generate variations service  
@app.route("/variations" , methods=['POST'])
def variations():
    jsonObject = json.loads(request.data)
    Question = jsonObject['Question1']
    variations = comb(Question)
    
    
    return {"variations": variations}

#generate questions from corpus service
@app.route("/corpusQuestions" , methods=['POST'])
def corpus():
    jsonObject = json.loads(request.data)
    inputText = jsonObject['Corpus']
    questionList = aqg.aqgParse(inputText)
    for x in range(questionList.count('\n')):
        questionList.remove('\n')
    
    return {"questions": questionList}


#get intent list
@app.route("/intentlist", methods=['POST'])
def intentlist():
    list1= list(term.keys())   
    return {"intents": list1}

#getQuestions and Response for an intent
@app.route("/QandR", methods=['POST'])
def QandR():
    jsonObject = json.loads(request.data)
    intentname = jsonObject['iname']
    qlist = term[intentname]
    interm = "utter_"+intentname
    res = newdict[interm]    
    return {"Qlist": qlist,"Response":res}


#if __name__ == '__main__':
#    app.run(host='0.0.0.0', port='5000')
    
    
    




    
    
    
    
    