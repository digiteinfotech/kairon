import yaml

class load():
    def load_intent(self, nlu_path):
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
        return term
    
    def load_domain(self, domain_path):
        with open(domain_path) as g:
            data1 = yaml.load(g, Loader=yaml.FullLoader)
            data2 = data1["templates"]
        newdict=dict()
        for keys in data2:

            data3 = data2[keys]
            data4=data3[0]
            data5 = data4["text"]
            newdict[keys]= data5
            
        return newdict
    
    def load_story(self, stories_path,term,newdict):
        dictrand={}
        with open(stories_path, 'r') as h:
            text2 = h.readlines()
        for line8 in text2:

            if "*" in line8:
                line9 = line8.replace("*","")
                line9= line9.strip()
                if line9 in list(term.keys()):
                    first = line9

            if "##" not in line8 and "*" not in line8 and "-" in line8:
                line6 = line8.replace("-","")
                line6 = line6.strip()
                if line6 in list(newdict.keys()):
                    second = line6
                    dictrand[first]= second
                    
        return dictrand

