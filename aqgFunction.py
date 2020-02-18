import spacy
import clause
import nonClause
import identification
import questionValidation
from nlpNER import nerTagger


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
                            questionsList += clause.howmuch_2(segmentSets, j, ner)
                        except Exception:
                            pass

                        if identification.clause_identify(segmentSets[j]) == 1:
                            try:
                                questionsList += clause.whom_1(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.whom_2(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.whom_3(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.whose(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.what_to_do(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.who(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.howmuch_1(segmentSets, j, ner)
                            except Exception:
                                pass
                            try:
                                questionsList += clause.howmuch_3(segmentSets, j, ner)
                            except Exception:
                                pass


                            else:
                                try:
                                    s = identification.subjectphrase_search(segmentSets, j)
                                

                                    if len(s) != 0:
                                        segmentSets[j] = s + segmentSets[j]
                                        try:
                                            questionsList += clause.whom_1(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += clause.whom_2(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += clause.whom_3(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += clause.whose(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += clause.what_to_do(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += clause.who(segmentSets, j, ner)
                                        except Exception:
                                            pass

                                    else:
                                        try:
                                            questionsList += nonClause.what_whom1(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += nonClause.what_whom2(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += nonClause.whose(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += nonClause.howmany(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                        try:
                                            questionsList += nonClause.howmuch_1(segmentSets, j, ner)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass


                questionsList.append('\n')
        return questionsList



    def DisNormal(self, str):
        print("\n")
        print("------X------")
        print("Start  output:\n")

        count = 0
        out = ""

        for i in range(len(str)):
            count = count + 1
            print("Q-0%d: %s" % (count, str[i]))

        print("")
        print("End  OutPut")
        print("-----X-----\n\n")


    # AQG Display the Generated Question
    def display(self, str):

        final = []
        count = 0
        #out = ""
        for i in range(len(str)):
            if (len(str[i]) >= 3):
                if (questionValidation.hNvalidation(str[i]) == 1):
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
                                
                               # print("Q-0%d: %s" % (count, str[i]))
                                #out += "Q-0" + count.__str__() + ": " + str[i] + "\n"
                            else:
                                final.append(str[i])
                               # print("Q-%d: %s" % (count, str[i]))
                                #out += "Q-" + count.__str__() + ": " + str[i] + "\n"
        return list(set(final))


