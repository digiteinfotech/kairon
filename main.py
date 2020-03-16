from bot_trainer import aqgFunction


# Main Function
def main():
    # Create AQG object
    aqg = aqgFunction.AutomaticQuestionGenerator()

    inputTextPath = "input file path -- ?? ../DB/db.txt"
    readFile = open(inputTextPath, 'r+', encoding="utf8")
    #readFile = open(inputTextPath, 'r+', encoding="utf8", errors = 'ignore')

    inputText = readFile.read()
    #inputText = '''I am Dipta. I love codding. I build my carrier with this.'''

    questionList = aqg.aqgParse(inputText)
    aqg.display(questionList)

    #aqg.DisNormal(questionList)

    return 0


# Call Main Function
if __name__ == "__main__":
    main()

