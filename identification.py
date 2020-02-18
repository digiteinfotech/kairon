import nltk


def chunk_search(segment, chunked):
    m = len(chunked)
    list1 = []
    for j in range(m):
        if (len(chunked[j]) > 2 or len(chunked[j]) == 1):
            list1.append(j)
        if (len(chunked[j]) == 2):
            try:
                str1 = chunked[j][0][0] + " " + chunked[j][1][0]
            except Exception:
                pass
            else:
                if (str1 in segment) == True:
                    list1.append(j)
    return list1

def segment_identify(sen):
    segment_set = sen.split(",")
    return segment_set


def clause_identify(segment):
    tok = nltk.word_tokenize(segment)
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?|VB.?|MD|RP>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    flag = 0
    for j in range(len(chunked)):
        if (len(chunked[j]) > 2):
            flag = 1
        if (len(chunked[j]) == 2):
            try:
                str1 = chunked[j][0][0] + " " + chunked[j][1][0]
            except Exception:
                pass
            else:
                if (str1 in segment) == True:
                    flag = 1
        if flag == 1:
            break

    return flag


def verbphrase_identify(clause):
    tok = nltk.word_tokenize(clause)
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)
    str1 = ""
    str2 = ""
    str3 = ""
    list1 = chunk_search(clause, chunked)
    if len(list1) != 0:
        m = list1[len(list1) - 1]
        for j in range(len(chunked[m])):
            str1 += chunked[m][j][0]
            str1 += " "

    tok1 = nltk.word_tokenize(str1)
    tag1 = nltk.pos_tag(tok1)
    gram1 = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*}"""
    chunkparser1 = nltk.RegexpParser(gram1)
    chunked1 = chunkparser1.parse(tag1)

    list2 = chunk_search(str1, chunked1)
    if len(list2) != 0:

        m = list2[0]
        for j in range(len(chunked1[m])):
            str2 += (chunked1[m][j][0] + " ")

    tok1 = nltk.word_tokenize(str1)
    tag1 = nltk.pos_tag(tok1)
    gram1 = r"""chunk:{<VB.?|MD|RP>+}"""
    chunkparser1 = nltk.RegexpParser(gram1)
    chunked2 = chunkparser1.parse(tag1)

    list3 = chunk_search(str1, chunked2)
    if len(list3) != 0:

        m = list3[0]
        for j in range(len(chunked2[m])):
            str3 += (chunked2[m][j][0] + " ")

    X = ""
    str4 = ""
    st = nltk.word_tokenize(str3)
    if len(st) > 1:
        X = st[0]
        s = ""
        for k in range(1, len(st)):
            s += st[k]
            s += " "
        str3 = s
        str4 = X + " " + str2 + str3

    if len(st) == 1:
        tag1 = nltk.pos_tag(st)
        if tag1[0][0] != 'are' and tag1[0][0] != 'were' and tag1[0][0] != 'is' and tag1[0][0] != 'am':
            if tag1[0][1] == 'VB' or tag1[0][1] == 'VBP':
                X = 'do'
            if tag1[0][1] == 'VBD' or tag1[0][1] == 'VBN':
                X = 'did'
            if tag1[0][1] == 'VBZ':
                X = 'does'
            str4 = X + " " + str2 + str3
        if (tag1[0][0] == 'are' or tag1[0][0] == 'were' or tag1[0][0] == 'is' or tag1[0][0] == 'am'):
            str4 = tag1[0][0] + " " + str2

    return str4


def subjectphrase_search(segment_set, num):
    str2 = ""
    for j in range(num - 1, 0, -1):
        str1 = ""
        flag = 0
        tok = nltk.word_tokenize(segment_set[j])
        tag = nltk.pos_tag(tok)
        gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
        chunkparser = nltk.RegexpParser(gram)
        chunked = chunkparser.parse(tag)

        list1 = chunk_search(segment_set[j], chunked)
        if len(list1) != 0:
            m = list1[len(list1) - 1]
            for j in range(len(chunked[m])):
                str1 += chunked[m][j][0]
                str1 += " "

            tok1 = nltk.word_tokenize(str1)
            tag1 = nltk.pos_tag(tok1)
            gram1 = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+}"""
            chunkparser1 = nltk.RegexpParser(gram1)
            chunked1 = chunkparser1.parse(tag1)

            list2 = chunk_search(str1, chunked1)
            if len(list2) != 0:
                m = list2[len(list2) - 1]
                for j in range(len(chunked1[m])):
                    str2 += (chunked1[m][j][0] + " ")
                flag = 1

        if flag == 0:
            tok1 = nltk.word_tokenize(segment_set[j])
            tag1 = nltk.pos_tag(tok1)
            gram1 = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+}"""
            chunkparser1 = nltk.RegexpParser(gram1)
            chunked1 = chunkparser1.parse(tag1)

            list2 = chunk_search(str1, chunked1)
            st = nltk.word_tokenize(segment_set[j])
            if len(chunked1[list2[0]]) == len(st):
                str2 = segment_set[j]
                flag = 1

        if flag == 1:
            break

    return str2


def postprocess(string):
    tok = nltk.word_tokenize(string)
    tag = nltk.pos_tag(tok)

    str1 = tok[0].capitalize()
    str1 += " "
    if len(tok) != 0:
        for i in range(1, len(tok)):
            if tag[i][1] == "NNP":
                str1 += tok[i].capitalize()
                str1 += " "
            else:
                str1 += tok[i].lower()
                str1 += " "
        tok = nltk.word_tokenize(str1)
        str1 = ""
        for i in range(len(tok)):
            if tok[i] == "i" or tok[i] == "we":
                str1 += "you"
                str1 += " "
            elif tok[i] == "my" or tok[i] == "our":
                str1 += "your"
                str1 += " "
            elif tok[i] == "your":
                str1 += "my"
                str1 += " "
            elif tok[i] == "you":
                if i - 1 >= 0:
                    to = nltk.word_tokenize(tok[i - 1])
                    ta = nltk.pos_tag(to)
                    # print ta
                    if ta[0][1] == 'IN':
                        str1 += "me"
                        str1 += " "
                    else:
                        str1 += "i"
                        str1 += " "
                else:
                    str1 += "i "

            elif tok[i] == "am":
                str1 += "are"
                str1 += " "
            else:
                str1 += tok[i]
                str1 += " "

    return str1

