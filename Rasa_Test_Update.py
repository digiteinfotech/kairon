#!/usr/bin/env python
# coding: utf-8

# In[45]:


#import libraries
import flair
from flair.data import Sentence
from flair.models import SequenceTagger
import pandas as pd
import numpy as np
import nltk
from nltk.corpus import wordnet
from nltk import ngrams
from nltk.corpus import stopwords 
from nltk.tokenize import RegexpTokenizer
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
import re
#from gingerit.gingerit import GingerIt
import gensim
from autocorrect import Speller
import os
import glob
import requests
import json
import tkinter as tk
from tkinter import *
from tkinter import ttk
from tkinter import filedialog as fd
import yaml
import nest_asyncio
import asyncio
from rasa.core.agent import Agent
from rasa.core.interpreter import RasaNLUInterpreter
from rasa import train
nest_asyncio.apply()
lemmatizer = WordNetLemmatizer()


# In[46]:


entity_helpverb_words = ['digite','agile','am', 'is', 'are','was', 'were', 'being', 'been', 'be','for','swiftly','in',
'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should','im','there','here','on','or','how','of',
                         'where','when','may', 'might', 'must', 'can', 'could','the','swiftalm', 'swift','kanban',
                         'alm','sap','cloud','scrum','jira','to','re','ve','mnc','wan','na','m','with','not']


# In[47]:


pos = SequenceTagger.load('pos-fast')


# In[48]:


m = gensim.models.KeyedVectors.load_word2vec_format(r'D:\\wiki-news-300d-1M.vec') # Change path as per model location


# In[49]:


def get_wordnet_pos(word):
    """Map POS tag to first character lemmatize() accepts"""
    tag = nltk.pos_tag([word])[0][1][0].upper()
    tag_dict = {"J": wordnet.ADJ,
                "N": wordnet.NOUN,
                "V": wordnet.VERB,
                "R": wordnet.ADV}

    return tag_dict.get(tag, wordnet.NOUN)


# In[50]:


async def sdw():
    accepttext = question_Text.get('1.0',END)
    Prediction = await agent.parse_message_using_nlu_interpreter(message_data=accepttext, tracker=None)
    Prediction = Prediction["intent"]['name']
    return Prediction


# In[51]:


#predict button
def predict():
    
    loop = asyncio.get_event_loop()
    prediction = loop.run_until_complete(sdw())
    
    P_Intent.delete('1.0', 'end')
    P_Intent.insert('insert', prediction)
    list1 = term[prediction]
    ICBOX.delete('1.0', 'end')
    for intent in list1:
        ICBOX.insert('insert', intent)
        ICBOX.insert('insert', "" + '\n')
    StatusBox.delete('1.0', 'end')
    StatusBox.insert('insert',"Intent Predicted")
    cbox.set('')
    cbox1.set('')


# In[52]:


#function to load nlu.md file
def load_data():
    global original_path, nlu_path, stories_path, models_path, domain_path, config_path, term, newdict, dictrand, train_path, agent
    original_path = fd.askdirectory(title = "Select the bot directory")
    nlu_path = original_path + "/data/nlu.md"
    stories_path = original_path + "/data/stories.md"
    models_path = original_path + "/models"
    domain_path = original_path + "/domain.yml"
    config_path = original_path + "/config.yml"
    train_path = original_path + "/data/"
    
    list_of_files1 = glob.glob(models_path+ "/*") # * means all if need specific format then *.csv
    latest_file1 = max(list_of_files1, key=os.path.getctime)
    modelpath = os.path.abspath(latest_file1)
    
    agent = Agent.load(modelpath)
    
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
    cbox1.config(values=list(term.keys()))
    RCOMB.config(values=list(term.keys()))
    RCOMB1.config(values=list(term.keys()))
    
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
        ####### else :
        
    
    
    StatusBox.delete('1.0', 'end')
    StatusBox.insert('insert',"Files Loaded")


# In[53]:


#Yes/No combobox function
def decision(self):
    if cbox.get() == 'Yes':
        StatusBox.delete('1.0', 'end')
        StatusBox.insert('insert',"Enter New Question")
        ICBOX.delete('1.0', 'end')
        P_Intent.delete('1.0', 'end')
        cbox.set('')
        cbox1.set('')
        question_Text.delete('1.0','end')
    else :
        StatusBox.delete('1.0', 'end')
        StatusBox.insert('insert',"Choose intent from list")
        ICBOX.delete('1.0', 'end')
        P_Intent.delete('1.0', 'end')        


# In[54]:


#Intent list combobox function
def decision1(self):
    RCOMB.set('')
    RCOMB1.set('')
    pick = cbox1.get()
    list2 = term[pick]
    ICBOX.delete('1.0', 'end')
    for intent1 in list2:
        ICBOX.insert('insert', intent1)
        ICBOX.insert('insert', "" + '\n')    


# In[55]:


def decision2(self):
    cbox1.set('')
    RCOMB1.set('')
    pick1 = RCOMB.get()
    list2 = term[pick1]
    ICBOX.delete('1.0', 'end')
    for intent1 in list2:
        ICBOX.insert('insert', intent1)
        ICBOX.insert('insert', "" + '\n') 


# In[56]:


def decision3(self):
    RCOMB.set('')
    cbox1.set('')
    pick3 = RCOMB1.get()
    list2 = term[pick3]
    ICBOX.delete('1.0', 'end')
    for intent1 in list2:
        ICBOX.insert('insert', intent1)
        ICBOX.insert('insert', "" + '\n') 


# In[57]:


#Add button
def Add():
    from tkinter import messagebox
    NameBox.delete('1.0', 'end')
    if question_Text.get('1.0',END) == '' or cbox1.get() == '':
        tk.messagebox.showinfo('Error', 'Please Enter Required Fields.')
        return
    else:
        global term
        updated = cbox1.get()
        list3 = term[updated]
        intermediate0 = question_Text.get('1.0',END).splitlines()
        intermediate1 = [ elem3 for elem3 in intermediate0 if elem3 != '']
        if len(intermediate1) == 0 :
            tk.messagebox.showinfo('Error', 'Please Enter Required Fields.')
            return
        
        intermediate1 = (" ".join(intermediate1))
        list3.append(intermediate1)
        ICBOX.delete('1.0', 'end')
        for intent5 in list3:
            intent5.strip()
            ICBOX.insert('insert', intent5)
            ICBOX.insert('insert', "" + '\n')
        tup = list3
        term[updated] = tup
        file_handler = open(nlu_path,'w')
        for finalkeys in list(term.keys()):

            file_handler.write('\n'+ "## intent:")
            file_handler.write(finalkeys)

            for value in term[finalkeys]:

                file_handler.write('\n'+ "- " + value)

            file_handler.write('\n')
        file_handler.close()
        
        current = list()
        current.append(intermediate1)
        comb(current)
        StatusBox.delete('1.0', 'end')
        StatusBox.insert('insert',"Changes Saved")


# In[58]:


## retrain button
def retrain():
    global agent
    os.chdir(original_path)
    train(domain= domain_path, config= config_path, training_files= train_path, force_training=False)
    
    list_of_files = glob.glob(models_path + '/*') # * means all if need specific format then *.csv
    latest_file = max(list_of_files, key=os.path.getctime)
    modelpath1 = os.path.abspath(latest_file)
    
    agent = Agent.load(modelpath1)
    
    StatusBox.delete('1.0', 'end')
    StatusBox.insert('insert',"Model Retrained")


# In[59]:


def finalAdd():
    global term
    from tkinter import messagebox
    nameb = NameBox.get('1.0',END).splitlines()
    nameb1 = [ elem1 for elem1 in nameb if elem1 != '']
    combo = combinations.get('1.0',END).splitlines()
    combo1 = [ elem1 for elem1 in combo if elem1 != '']
    if len(combo1) == 0:
        tk.messagebox.showinfo('Error', 'No text available.')
    elif cbox1.get() == '' and len(nameb1) == 0 :
        tk.messagebox.showinfo('Error', 'No intent specified')
    else:
        if cbox1.get() == '' :
            intent_name = nameb1[0]
        else:
            intent_name = cbox1.get()
        list_temp = term[intent_name]
        list_temp = list_temp + combo1
        term[intent_name] = list_temp
        
        file_handler = open(nlu_path,'w')
        for finalkeys in list(term.keys()):

            file_handler.write('\n'+ "## intent:")
            file_handler.write(finalkeys)

            for value in term[finalkeys]:

                file_handler.write('\n'+ "- " + value)

            file_handler.write('\n')
        file_handler.close()
        
        StatusBox.delete('1.0', 'end')
        StatusBox.insert('insert',"Variations Recorded")


# In[60]:


def Add1():
    global term, newdict, dictrand
    from tkinter import messagebox
    
    IntentName1 = NameBox.get('1.0',END).splitlines()
    IntentResponse1 = rbox.get('1.0',END).splitlines()
    TrainQuestions1 = TICBOX.get('1.0',END).splitlines()
    IntentName= [ elem for elem in IntentName1 if elem != '']
    IntentResponse = [ elem1 for elem1 in IntentResponse1 if elem1 != '']
    TrainQuestions = [ elem2 for elem2 in TrainQuestions1 if elem2 != '']
    
    if len(IntentName) == 0 or len(IntentResponse) == 0:
        tk.messagebox.showinfo('Error', 'Please Enter Required Fields.')
        return
        
    elif len(TrainQuestions)<5 :
        tk.messagebox.showinfo('Error', 'Minimum 5 Questions/Sentences required.')
        return
    else:
        cbox1.set('')
        IntentResponse = ("\n".join(IntentResponse))
        if IntentName[0] == 'default' or IntentName[0] in list(term.keys()) or "intent" in IntentName[0]:
            tk.messagebox.showinfo('Error', 'Intent Name Not Accepted. Try another name.')
            return
        else:
            comb(TrainQuestions)
            intent = IntentName[0]
            response = IntentResponse
            action = "utter_"+intent
            Questions = TrainQuestions
            
            term[intent] = TrainQuestions
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
                documents = yaml.dump(finaldict, file)
            
            file_handler = open(stories_path,'w')
            for key2 in dictrand:
                file_handler.write('\n'+ "## " + "path_" + key2 )
                file_handler.write('\n'+ "* " + key2)
                file_handler.write('\n'+ "  - " + dictrand[key2])

                file_handler.write('\n')
            file_handler.close()
            
            StatusBox.delete('1.0', 'end')
            StatusBox.insert('insert',"Intent Added")
            cbox1.config(values=list(term.keys()))
            RCOMB.config(values=list(term.keys()))
            RCOMB1.config(values=list(term.keys()))


# In[61]:


def Rem():
    from tkinter import messagebox
    global term
    selection1 = REMBOX.get('1.0',END).splitlines()
    selection1 = [ elem1 for elem1 in selection1 if elem1 != '']
    selection = RCOMB.get()
    
    if len(selection1) == 0 or RCOMB.get() == '':
        tk.messagebox.showinfo('Error', 'Please Enter Required Fields.')
        return
    else:
        selection1 = (" ".join(selection1))
        pick8 = term[selection]
        if selection1 in pick8:
            pick8.remove(selection1)
            term[selection] = pick8
            
            ICBOX.delete('1.0', 'end')
            for intent1 in pick8:
                intent1.strip()
                ICBOX.insert('insert', intent1)
                ICBOX.insert('insert', "" + '\n')
            
            StatusBox.delete('1.0', 'end')
            StatusBox.insert('insert',"Changes Saved")
            
            file_handler = open(nlu_path,'w')
            for finalkeys in list(term.keys()):

                file_handler.write('\n'+ "## intent:")
                file_handler.write(finalkeys)

                for value in term[finalkeys]:

                    file_handler.write('\n'+ "- " + value)

                file_handler.write('\n')
            file_handler.close()
        
        else:
            tk.messagebox.showinfo('Error', 'Sentence not in Specified intent.')
            


# In[62]:


def Rem1():
    global term, newdict, dictrand
    from tkinter import messagebox
    if RCOMB1.get()=='':
        tk.messagebox.showinfo('Error', 'Please Enter Intent.')
    else:
        req1 = RCOMB1.get()
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
            documents = yaml.dump(finaldict, file)

        file_handler = open(stories_path,'w')
        for key2 in dictrand:
            file_handler.write('\n'+ "## " + "path_" + key2 )
            file_handler.write('\n'+ "* " + key2)
            file_handler.write('\n'+ "  - " + dictrand[key2])

            file_handler.write('\n')
        file_handler.close()
        
        StatusBox.delete('1.0', 'end')
        StatusBox.insert('insert',"Intent Removed")
        cbox1.config(values=list(term.keys()))
        RCOMB.config(values=list(term.keys()))
        RCOMB1.config(values=list(term.keys()))   
        RCOMB1.set('')
        ICBOX.delete('1.0', 'end')      


# In[63]:


def comb(lis):
    combinations.delete('1.0', 'end')
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
            
    ##################################################################################################
        #listf1=[]
        #parser = GingerIt()
        #for sent in collective2:
        #    try:
        #        res = parser.parse(sent)
        #        res1 = res['result']
        #        res1 = res1.lower()
        #        listf1.append(res1)

        #    except:
        #        listf1.append(sent)
     ##################################################################################################       
        

        for intent in collective2:
            combinations.insert('insert', intent)
            combinations.insert('insert', "" + '\n')   


# In[64]:


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


# In[65]:


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


# In[66]:


def Reject():
    combinations.delete('1.0', 'end')


# In[ ]:


#GUI
rootFrame = tk.Tk()
rootFrame.state('zoomed')
rootFrame.title("Bot Manipulation")

#############################################################################################################################
rootFrame.columnconfigure(0, pad=3)
rootFrame.columnconfigure(1, pad=3)
rootFrame.columnconfigure(2, pad=3)
rootFrame.columnconfigure(3, pad=3)
rootFrame.columnconfigure(4, pad=3)
rootFrame.columnconfigure(5, pad=3)
rootFrame.columnconfigure(6, pad=3)
rootFrame.columnconfigure(7, pad=3)
rootFrame.columnconfigure(8, pad=3)
rootFrame.columnconfigure(9, pad=3)

#########################################################################################################################

rootFrame.rowconfigure(0, pad=3)
rootFrame.rowconfigure(1, pad=3)
rootFrame.rowconfigure(2, pad=3)
rootFrame.rowconfigure(3, pad=3)
rootFrame.rowconfigure(4, pad=3)
rootFrame.rowconfigure(5, pad=3)
rootFrame.rowconfigure(6, pad=3)
rootFrame.rowconfigure(7, pad=3)
rootFrame.rowconfigure(8, pad=3)
rootFrame.rowconfigure(9, pad=3)
rootFrame.rowconfigure(10, pad=3)
rootFrame.rowconfigure(11, pad=3)
rootFrame.rowconfigure(12, pad=3)
rootFrame.rowconfigure(13, pad=3)
rootFrame.rowconfigure(14, pad=3)
rootFrame.rowconfigure(15, pad=3)
rootFrame.rowconfigure(16, pad=3)
rootFrame.rowconfigure(17, pad=3)
rootFrame.rowconfigure(18, pad=3)
rootFrame.rowconfigure(19, pad=3)
rootFrame.rowconfigure(20, pad=3)
rootFrame.rowconfigure(21, pad=3)
rootFrame.rowconfigure(22, pad=3)
rootFrame.rowconfigure(23, pad=3)
rootFrame.rowconfigure(24, pad=3)
rootFrame.rowconfigure(25, pad=3)
rootFrame.rowconfigure(26, pad=3)
rootFrame.rowconfigure(27, pad=3)
rootFrame.rowconfigure(28, pad=3)
rootFrame.rowconfigure(29, pad=3)
rootFrame.rowconfigure(30, pad=3)
rootFrame.rowconfigure(31, pad=3)
rootFrame.rowconfigure(32, pad=3)
rootFrame.rowconfigure(33, pad=3)


LoadButton = tk.Button(rootFrame, text='Load bot directory', command = lambda: load_data())
LoadButton.grid(row=0, column = 0, padx = 10 )
#######################################################################################################################

question_label = tk.Label(rootFrame, text = 'Enter Query/Add Component')
question_label.grid(row=1, column=0, padx = 2)
question_Text = tk.Text(rootFrame,height=1,width = 32)
question_Text.grid(row=2, column = 0, columnspan = 3,padx=5,sticky = "W")

######################################################################################################################
PredictButton = tk.Button(rootFrame, text='Predict', command = lambda: predict())
PredictButton.grid(row=2, column = 1)
#######################################################################################################################
intent_label = tk.Label(rootFrame, text = 'Predicted intent')
intent_label.grid(row=3, column=0, padx = 2)

P_Intent = tk.Text(rootFrame, height=1, width = 20, bg='light grey')
P_Intent.grid(row=4, column=0,padx=2)

#######################################################################################################################
correct_label = tk.Label(rootFrame, text = 'Is this correct?')
correct_label.grid(row=5, column=0, padx = 2)

cbox = ttk.Combobox(rootFrame,values=['Yes','No'],width = 3)
cbox.grid(row = 5, column = 1,sticky='W')
cbox.bind("<<ComboboxSelected>>", decision)

################################################################################################################
StatusBox_Label = tk.Label(rootFrame, text = 'Status')
StatusBox_Label.grid(row=19, column = 4, padx = 2)

StatusBox = tk.Text(rootFrame, height=1, width = 44, bg='light grey')
StatusBox.grid(row=20, column = 4, padx = 2,rowspan = 4,columnspan = 2)



################################################################################################################

IL = tk.Label(rootFrame, text = 'Intent List')
IL.grid(row=7, column=0, padx = 2)

cbox1 = ttk.Combobox(rootFrame)
cbox1.grid(row = 7, column = 1,sticky='W')
cbox1.bind("<<ComboboxSelected>>", decision1)

###################################################################################################################

IC = tk.Label(rootFrame, text = 'Intent Components')
IC.grid(row=8, column=0, padx = 2)

ICBOX = tk.Text(rootFrame, height=10, width = 44, bg='light grey')
ICBOX.grid(row=9, rowspan = 5, column = 0, columnspan = 2, padx = 4)

scrollbar1 = tk.Scrollbar(rootFrame)
ICBOX.config(yscrollcommand= scrollbar1.set)
scrollbar1.config(command= ICBOX.yview)
scrollbar1.grid(column=2, row=9, rowspan=5,sticky = 'NSW')

##################################################################################################################
AddButton = tk.Button(rootFrame, text='Add',width =5,command = lambda: Add())
AddButton.grid(row=14, column = 0, padx =2,pady=5)

##################################################################################################################

RetrainButton = tk.Button(rootFrame, text='Retrain',command = lambda: retrain())
RetrainButton.grid(row=25, column = 4, padx=2,pady=2)

##################################################################################################################

Create = tk.Label(rootFrame, text = 'Create Intent')
Create.grid(row=0, column=3, padx = 2)

Name = tk.Label(rootFrame, text = 'Name :')
Name.grid(row=1, column=3)

NameBox = tk.Text(rootFrame, height=1, width = 20)
NameBox.grid(row=1, column=4,padx=2, sticky="W")

TComponents = tk.Label(rootFrame, text = 'Training Data/Questions :')
TComponents.grid(row=2, column=3)

TICBOX = tk.Text(rootFrame,wrap=NONE, height=10, width = 44)
TICBOX.grid(row=3, rowspan = 7, column = 4, columnspan = 2, padx = 2)

scrollbar2 = tk.Scrollbar(rootFrame)
TICBOX.config(yscrollcommand= scrollbar2.set)
scrollbar2.config(command= TICBOX.yview)
scrollbar2.grid(column=8, row=3, rowspan=7,sticky = 'NSW')

scrollbar3 = tk.Scrollbar(rootFrame , orient = HORIZONTAL)
TICBOX.config(xscrollcommand= scrollbar3.set)
scrollbar3.config(command= TICBOX.xview)
scrollbar3.grid(column=4, row=10, columnspan= 3,sticky = 'NEW')

response = tk.Label(rootFrame, text = 'Response :')
response.grid(row=10, column=3)

rbox = tk.Text(rootFrame, height=4, width = 44)
rbox.grid(row=10, rowspan = 4, column = 4, columnspan = 2, padx = 2)

scrollbar4 = tk.Scrollbar(rootFrame)
rbox.config(yscrollcommand= scrollbar4.set)
scrollbar4.config(command= rbox.yview)
scrollbar4.grid(column=8, row=10, rowspan=3,sticky = 'NSW')

AddButton1 = tk.Button(rootFrame, text='Add',width =5,command = lambda: Add1())
AddButton1.grid(row=14, column = 4, padx =2,sticky="W")

#######################################################################################################################

RCOM = tk.Label(rootFrame, text = 'Remove Sentence')
RCOM.grid(row=15, column=0, pady=20)

Int = tk.Label(rootFrame, text = 'Intent :')
Int.grid(row=16, column=0)

RCOMB = ttk.Combobox(rootFrame)
RCOMB.grid(row = 16, column = 1)
RCOMB.bind("<<ComboboxSelected>>", decision2)

REMBOX = tk.Text(rootFrame, height=1, width = 44)
REMBOX.grid(row=17, column = 0,columnspan=2, padx = 2, sticky='W')

RemButton = tk.Button(rootFrame, text='Remove',command = lambda: Rem())
RemButton.grid(row=18, column = 0, padx =2)

########################################################################################################################

Rint = tk.Label(rootFrame, text = 'Remove Intent')
Rint.grid(row=15, column=4)

RCOMB1 = ttk.Combobox(rootFrame)
RCOMB1.grid(row = 16, column = 4)
RCOMB1.bind("<<ComboboxSelected>>", decision3)

RemButton1 = tk.Button(rootFrame, text='Remove',command = lambda: Rem1())
RemButton1.grid(row=17, column = 4, padx =2)

########################################################################################################################

variations = tk.Label(rootFrame, text = 'Variations')
variations.grid(row=2, column=8)

combinations =tk.Text(rootFrame,wrap=NONE, height=20, width = 44)
combinations.grid(row=3, rowspan = 12, column = 8,columnspan = 2, padx = 30)

scrollbar5 = tk.Scrollbar(rootFrame)
combinations.config(yscrollcommand= scrollbar5.set)
scrollbar5.config(command= combinations.yview)
scrollbar5.grid(column=9, row=3, rowspan=12,sticky = 'NSE')

scrollbar6 = tk.Scrollbar(rootFrame , orient = HORIZONTAL)
combinations.config(xscrollcommand= scrollbar6.set)
scrollbar6.config(command= combinations.xview)
scrollbar6.grid(column=8, row=15, columnspan= 2,sticky = 'NEW')

finaladd = tk.Button(rootFrame, text='Add',command = lambda: finalAdd())
finaladd.grid(row=15, column = 8, padx =2)

reject = tk.Button(rootFrame, text='Reject',command = lambda: Reject())
reject.grid(row=15, column = 9, padx =2)


rootFrame.mainloop()


# In[ ]:




