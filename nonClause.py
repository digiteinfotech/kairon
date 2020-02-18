import nltk
import identification


def get_chunk(chunked):
    str1 = ""
    for j in range(len(chunked)):
        str1 += (chunked[j][0] + " ")
    return str1

def what_whom1(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<TO>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|VBG|DT|POS|CD|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    s = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                if chunked[j][1][1] == 'PRP':
                    str2 = "to whom "
                else:
                    for x in range(len(chunked[j])):
                        if (chunked[j][x][1] == "NNP" or chunked[j][x][1] == "NNPS" or chunked[j][x][1] == "NNS" or
                                chunked[j][x][1] == "NN"):
                            break

                    for x1 in range(len(ner)):
                        if ner[x1][0] == chunked[j][x][0]:
                            if ner[x1][1] == "PERSON":
                                str2 = " to whom "
                            elif ner[x1][1] == "LOC" or ner[x1][1] == "ORG" or ner[x1][1] == "GPE":
                                str2 = " where "
                            elif ner[x1][1] == "TIME" or ner[x1][1] == "DATE":
                                str2 = " when "
                            else:
                                str2 = "to what"

                str4 = str1 + str2 + str3
                for k in range(len(segment_set)):
                    if k != num:
                        str4 += ("," + segment_set[k])
                str4 += '?'
                str4 = identification.postprocess(str4)
                # str4 = 'Q.' + str4
                s.append(str4)
    return s


def what_whom2(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<IN>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|POS|VBG|DT|CD|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)
    list1 = identification.chunk_search(segment_set[num], chunked)
    s = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                if chunked[j][1][1] == 'PRP':
                    str2 = " " + chunked[j][0][0] + " whom "
                else:
                    for x in range(len(chunked[j])):
                        if (chunked[j][x][1] == "NNP" or chunked[j][x][1] == "NNPS" or chunked[j][x][1] == "NNS" or
                                chunked[j][x][1] == "NN"):
                            break

                    for x1 in range(len(ner)):
                        if ner[x1][0] == chunked[j][x][0]:
                            if ner[x1][1] == "PERSON":
                                str2 = " " + chunked[j][0][0] + "whom "
                            elif ner[x1][1] == "LOC" or ner[x1][1] == "ORG" or ner[x1][1] == "GPE":
                                str2 = " where "
                            elif ner[x1][1] == "TIME" or ner[x1][1] == "DATE":
                                str2 = " when "
                            else:
                                str2 = " " + chunked[j][0][0] + " what"

                str4 = str1 + str2 + str3
                for k in range(len(segment_set)):
                    if k != num:
                        str4 += ("," + segment_set[k])
                str4 += '?'
                str4 = identification.postprocess(str4)
                # str4 = 'Q.' + str4
                s.append(str4)
    return s


def whose(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<NN.?>*<PRP\$|POS>+<RB.?>*<JJ.?>*<NN.?|VBG|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    s = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str3 = ""
            str2 = " whose "
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")
                if chunked[j][1][1] == 'POS':
                    for k in range(2, len(chunked[j])):
                        str2 += (chunked[j][k][0] + " ")
                else:
                    for k in range(1, len(chunked[j])):
                        str2 += (chunked[j][k][0] + " ")

                str4 = str1 + str2 + str3
                for k in range(len(segment_set)):
                    if k != num:
                        str4 += ("," + segment_set[k])
                str4 += '?'
                str4 = identification.postprocess(str4)
                # str4 = 'Q.' + str4
                s.append(str4)
    return s


def howmany(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<DT>?<CD>+<RB>?<JJ|JJR|JJS>?<NN|NNS|NNP|NNPS|VBG>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    s = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str3 = ""
            str2 = " how many "
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                st = get_chunk(chunked[j])
                tok = nltk.word_tokenize(st)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<RB>?<JJ|JJR|JJS>?<NN|NNS|NNP|NNPS|VBG>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(st, chunked1)
                z = ""

                for k in range(len(chunked1)):
                    if k in list2:
                        z += get_chunk(chunked1[k])

                str4 = str1 + str2 + z + str3
                for k in range(len(segment_set)):
                    if k != num:
                        str4 += ("," + segment_set[k])
                str4 += '?'
                str4 = identification.postprocess(str4)
                # str4 = 'Q.' + str4
                s.append(str4)
    return s


def howmuch_1(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<IN>+<\$>?<CD>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    s = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str3 = ""
            str2 = " how much "
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                str2 = chunked[j][0][0] + str2
                str4 = str1 + str2 + str3
                for k in range(len(segment_set)):
                    if k != num:
                        str4 += ("," + segment_set[k])
                str4 += '?'
                str4 = identification.postprocess(str4)
                # str4 = 'Q.' + str4
                s.append(str4)
    return s

