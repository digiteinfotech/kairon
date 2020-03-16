import spacy
from bot_trainer.clause import howmuch_2, howmuch_1 as c_howmuch_1, howmuch_3, what_to_do, who, whom_1, whom_2, whom_3, whose as c_whose
from bot_trainer.nonClause import whose, howmuch_1,  howmany, what_whom1, what_whom2
from bot_trainer.identification import clause_identify, subjectphrase_search
from bot_trainer.questionValidation import hNvalidation
from bot_trainer.nlpNER import nerTagger


class AutomaticQuestionGenerator():
    # AQG Parsing & Generate a question
    def aqgParse(self, sentence):

        #nlp = spacy.load("en")
        nlp = spacy.load('en_core_web_sm')

        singleSentences = sentence.split(".")
        questionsList = []
        if len(singleSentences) != 0:
            for i in range(len(singleSentences)):
                segmentSets = singleSentences[i].split(",")

                ner = nerTagger(nlp, singleSentences[i])

                if (len(segmentSets)) != 0:
                    for j in range(len(segmentSets)):
                        try:
                            questionsList += howmuch_2(segmentSets, j, ner)
                        except Exception:
                            pass

                        if clause_identify(segmentSets[j]) == 1:
                            try:
                                questionsList += whom_1(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += whom_2(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += whom_3(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += c_whose(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += what_to_do(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += who(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += c_howmuch_1(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += howmuch_3(segmentSets, j, ner)
                            except Exception:
                                pass


                        else:
                            try:
                            
                                s = subjectphrase_search(segmentSets, j)
                                

                                if len(s) != 0:
                                    segmentSets[j] = s + segmentSets[j]
                                    try:
                                        questionsList += whom_1(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += whom_2(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += whom_3(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += c_whose(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += what_to_do(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += who(segmentSets, j, ner)
                                    except Exception:
                                        pass

                                else:
                                    try:
                                        questionsList += what_whom1(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += what_whom2(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += whose(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += howmany(segmentSets, j, ner)
                                    except Exception:
                                        pass
                                    try:
                                        questionsList += howmuch_1(segmentSets, j, ner)
                                    except Exception:
                                        pass
                            except:
                                pass

                questionsList.append('\n')
        return questionsList



    def DisNormal(self, str):
        print("\n")
        print("------X------")
        print("Start  output:\n")

        count = 0

        for i in range(len(str)):
            count = count + 1
            print("Q-0%d: %s" % (count, str[i]))

        print("")
        print("End  OutPut")
        print("-----X-----\n\n")


    # AQG Display the Generated Question
    def display(self, str):
        

        final=[]
        count = 0
        for i in range(len(str)):
            if (len(str[i]) >= 3):
                if (hNvalidation(str[i]) == 1):
                    if ((str[i][0] == 'W' and str[i][1] == 'h') or (str[i][0] == 'H' and str[i][1] == 'o') or (
                            str[i][0] == 'H' and str[i][1] == 'a')):
                        WH = str[i].split(',')
                        if (len(WH) == 1):
                            str[i] = str[i][:-1]
                            str[i] = str[i][:-1]
                            str[i] = str[i][:-1]
                            str[i] = str[i] + "?"
                            count = count + 1

                            if (count < 10):
                                final.append(str[i])
                                

                            else:
                                final.append(str[i])
                                

        return list(set(final))

        
