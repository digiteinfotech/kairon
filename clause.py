import nltk
import identification
import nonClause


def whom_1(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<TO>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|VBG|DT|POS|CD|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                if chunked[j][1][1] == 'PRP':
                    str2 = " to whom "
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
                                str2 = "to what "

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)
                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    st = str5 + str2 + str4 + str6 + str3
                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3


def whom_2(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<IN>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|POS|VBG|DT|CD|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
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
                                str2 = " " + chunked[j][0][0] + " whom "
                            elif ner[x1][1] == "LOC" or ner[x1][1] == "ORG" or ner[x1][1] == "GPE":
                                str2 = " where "
                            elif ner[x1][1] == "TIME" or ner[x1][1] == "DATE":
                                str2 = " when "
                            else:
                                str2 = " " + chunked[j][0][0] + " what "

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)
                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    st = str5 + str2 + str4 + str6 + str3
                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3


def whom_3(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<VB.?|MD|RP>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|POS|VBG|DT|CD|VBN>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                if chunked[j][1][1] == 'PRP':
                    str2 = " whom "
                else:
                    for x in range(len(chunked[j])):
                        if (chunked[j][x][1] == "NNP" or chunked[j][x][1] == "NNPS" or chunked[j][x][1] == "NNS" or
                                chunked[j][x][1] == "NN"):
                            break

                    for x1 in range(len(ner)):
                        if ner[x1][0] == chunked[j][x][0]:
                            if ner[x1][1] == "PERSON":
                                str2 = " whom "
                            elif ner[x1][1] == "LOC" or ner[x1][1] == "ORG" or ner[x1][1] == "GPE":
                                str2 = " what "
                            elif ner[x1][1] == "TIME" or ner[x1][1] == "DATE":
                                str2 = " what time "
                            else:
                                str2 = " what "

                strx = nonClause.get_chunk(chunked[j])
                tok = nltk.word_tokenize(strx)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<VB.?|MD>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                strx = nonClause.get_chunk(chunked1[0])

                str1 += strx

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)

                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    st = str5 + str2 + str4 + str6 + str3
                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3


def whose(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<DT|NN.?>*<PRP\$|POS>+<RB.?>*<JJ.?>*<NN.?|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for i in range(len(chunked)):
            if i in list1:
                str1 = ""
                str3 = ""
                str2 = ""
                for k in range(i):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")
                str1 += " whose "

                for k in range(i + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                if chunked[i][1][1] == 'POS':
                    for k in range(2, len(chunked[i])):
                        str2 += (chunked[i][k][0] + " ")

                if chunked[i][0][1] == 'PRP$':
                    for k in range(1, len(chunked[i])):
                        str2 += (chunked[i][k][0] + " ")

                str2 = str1 + str2 + str3
                str4 = ""

                for l in range(0, len(segment_set)):
                    if l < num:
                        str4 += (segment_set[l] + ",")
                    if l > num:
                        str2 += ("," + segment_set[l])
                str2 = str4 + str2
                str2 += '?'
                str2 = identification.postprocess(str2)
                # str2 = 'Q.' + str2
                list3.append(str2)

    return list3


def what_to_do(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<TO>+<VB|VBP|RP>+<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|POS|VBG|DT>*}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                ls = nonClause.get_chunk(chunked[j])
                tok = nltk.word_tokenize(ls)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<DT>?<RB.?>*<JJ.?>*<NN.?|PRP|PRP\$|POS|VBG|DT>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked2 = chunkparser.parse(tag)
                lis = identification.chunk_search(ls, chunked2)
                if len(lis) != 0:
                    x = lis[len(lis) - 1]
                    ls1 = nonClause.get_chunk(chunked2[x])
                    index = ls.find(ls1)
                    str2 = " " + ls[0:index]
                else:
                    str2 = " to do "

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)
                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    if chunked2[j][1][1] == 'PRP':
                        tr = " whom "
                    else:
                        for x in range(len(chunked[j])):
                            if (chunked[j][x][1] == "NNP" or chunked[j][x][1] == "NNPS" or chunked[j][x][1] == "NNS" or
                                    chunked[j][x][1] == "NN"):
                                break

                        for x1 in range(len(ner)):
                            if ner[x1][0] == chunked[j][x][0]:
                                if ner[x1][1] == "PERSON":
                                    tr = " whom "
                                elif ner[x1][1] == "LOC" or ner[x1][1] == "ORG" or ner[x1][1] == "GPE":
                                    tr = " where "
                                elif ner[x1][1] == "TIME" or ner[x1][1] == "DATE":
                                    tr = " when "
                                else:
                                    tr = " what "

                    st = str5 + tr + str4 + str2 + str6 + str3
                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3


def who(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(list1)):
            m = list1[j]
            str1 = ""
            for k in range(m + 1, len(chunked)):
                if k in list1:
                    str1 += nonClause.get_chunk(chunked[k])
                else:
                    str1 += (chunked[k][0] + " ")

            str2 = nonClause.get_chunk(chunked[m])
            tok = nltk.word_tokenize(str2)
            tag = nltk.pos_tag(tok)

            for m11 in range(len(tag)):
                if tag[m11][1] == 'NNP' or tag[m11][1] == 'NNPS' or tag[m11][1] == 'NNS' or tag[m11][1] == 'NN':
                    break
            s11 = ' who '
            for m12 in range(len(ner)):
                if ner[m12][0] == tag[m11][0]:
                    if ner[m12][1] == 'LOC':
                        s11 = ' which place '
                    elif ner[m12][1] == 'ORG':
                        s11 = ' who '
                    elif ner[m12][1] == 'DATE' or ner[m12][1] == 'TIME':
                        s11 = ' what time '
                    else:
                        s11 = ' who '

            gram = r"""chunk:{<RB.?>*<VB.?|MD|RP>+}"""
            chunkparser = nltk.RegexpParser(gram)
            chunked1 = chunkparser.parse(tag)

            list2 = identification.chunk_search(str2, chunked1)
            if len(list2) != 0:
                str2 = nonClause.get_chunk(chunked1[list2[0]])
                str2 = s11 + str2
                for k in range(list2[0] + 1, len(chunked1)):
                    if k in list2:
                        str2 += nonClause.get_chunk(chunked[k])
                    else:
                        str2 += (chunked[k][0] + " ")
                str2 += (" " + str1)

                tok_1 = nltk.word_tokenize(str2)
                str2 = ""
                for h in range(len(tok_1)):
                    if tok_1[h] == "am":
                        str2 += " is "
                    else:
                        str2 += (tok_1[h] + " ")

                for l in range(num + 1, len(segment_set)):
                    str2 += ("," + segment_set[l])
                str2 += '?'

                str2 = identification.postprocess(str2)
                # str2 = 'Q.' + str2
                list3.append(str2)

    return list3


def howmuch_2(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<\$>*<CD>+<MD>?<VB|VBD|VBG|VBP|VBN|VBZ|RP>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(list1)):
            m = list1[j]
            str1 = ""
            for k in range(m + 1, len(chunked)):
                if k in list1:
                    str1 += nonClause.get_chunk(chunked[k])
                else:
                    str1 += (chunked[k][0] + " ")

            str2 = nonClause.get_chunk(chunked[m])
            tok = nltk.word_tokenize(str2)
            tag = nltk.pos_tag(tok)
            gram = r"""chunk:{<RB.?>*<VB.?|MD|RP>+}"""
            chunkparser = nltk.RegexpParser(gram)
            chunked1 = chunkparser.parse(tag)
            s11 = ' how much '

            list2 = identification.chunk_search(str2, chunked1)
            if len(list2) != 0:
                str2 = nonClause.get_chunk(chunked1[list2[0]])
                str2 = s11 + str2
                for k in range(list2[0] + 1, len(chunked1)):
                    if k in list2:
                        str2 += nonClause.get_chunk(chunked[k])
                    else:
                        str2 += (chunked[k][0] + " ")
                str2 += (" " + str1)

                tok_1 = nltk.word_tokenize(str2)
                str2 = ""
                for h in range(len(tok_1)):
                    if tok_1[h] == "am":
                        str2 += " is "
                    else:
                        str2 += (tok_1[h] + " ")

                for l in range(num + 1, len(segment_set)):
                    str2 += ("," + segment_set[l])
                str2 += '?'

                str2 = identification.postprocess(str2)
                # str2 = 'Q.' + str2
                list3.append(str2)

    return list3


def howmuch_1(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<IN>+<\$>?<CD>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                str2 = ' ' + chunked[j][0][0] + ' how much '

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)
                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    st = str5 + str2 + str4 + str6 + str3
                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3


def howmuch_3(segment_set, num, ner):
    tok = nltk.word_tokenize(segment_set[num])
    tag = nltk.pos_tag(tok)
    gram = r"""chunk:{<MD>?<VB|VBD|VBG|VBP|VBN|VBZ>+<IN|TO>?<PRP|PRP\$|NN.?>?<\$>*<CD>+}"""
    chunkparser = nltk.RegexpParser(gram)
    chunked = chunkparser.parse(tag)

    list1 = identification.chunk_search(segment_set[num], chunked)
    list3 = []

    if len(list1) != 0:
        for j in range(len(chunked)):
            str1 = ""
            str2 = ""
            str3 = ""
            if j in list1:
                for k in range(j):
                    if k in list1:
                        str1 += nonClause.get_chunk(chunked[k])
                    else:
                        str1 += (chunked[k][0] + " ")

                for k in range(j + 1, len(chunked)):
                    if k in list1:
                        str3 += nonClause.get_chunk(chunked[k])
                    else:
                        str3 += (chunked[k][0] + " ")

                strx = nonClause.get_chunk(chunked[j])
                tok = nltk.word_tokenize(strx)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<MD>?<VB|VBD|VBG|VBP|VBN|VBZ>+<IN|TO>?<PRP|PRP\$|NN.?>?}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                strx = nonClause.get_chunk(chunked1[0])
                str1 += (" " + strx)

                str2 = ' how much '

                tok = nltk.word_tokenize(str1)
                tag = nltk.pos_tag(tok)
                gram = r"""chunk:{<EX>?<DT>?<JJ.?>*<NN.?|PRP|PRP\$|POS|IN|DT|CC|VBG|VBN>+<RB.?>*<VB.?|MD|RP>+}"""
                chunkparser = nltk.RegexpParser(gram)
                chunked1 = chunkparser.parse(tag)

                list2 = identification.chunk_search(str1, chunked1)

                if len(list2) != 0:
                    m = list2[len(list2) - 1]

                    str4 = nonClause.get_chunk(chunked1[m])
                    str4 = identification.verbphrase_identify(str4)
                    str5 = ""
                    str6 = ""

                    for k in range(m):
                        if k in list2:
                            str5 += nonClause.get_chunk(chunked1[k])
                        else:
                            str5 += (chunked1[k][0] + " ")

                    for k in range(m + 1, len(chunked1)):
                        if k in list2:
                            str6 += nonClause.get_chunk(chunked1[k])
                        else:
                            str6 += (chunked1[k][0] + " ")

                    st = str5 + str2 + str4 + str6 + str3

                    for l in range(num + 1, len(segment_set)):
                        st += ("," + segment_set[l])
                    st += '?'
                    st = identification.postprocess(st)
                    # st = 'Q.' + st
                    list3.append(st)

    return list3
