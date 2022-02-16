from ..question_generator.generator import QuestionGenerator


class TrainingDataGenerator:

    """Class contains logic to retrieve intents, training examples and responses from pdf and docx documents"""

    @staticmethod
    def helper_intent(node_index, branch_name, treedict, newlist):
        all_children = treedict.get(node_index)
        if all_children is None:
            return [[branch_name, newlist[node_index]]]
        lists_combined = []
        formated_name = '-'.join(newlist[node_index].split(' ')[1:])
        update_name_of_branch = branch_name + '_' + formated_name
        for child in all_children:
            lists_combined += TrainingDataGenerator.helper_intent(child, update_name_of_branch, treedict, newlist)
        return lists_combined

    @staticmethod
    def find_intents(node_index, branch_name, treedict, newlist):
        all_children = treedict.get(node_index)
        if all_children is None:
            return [[branch_name, TrainingDataGenerator.generate_question(newlist[node_index][4:])]]
        lists_combined = []
        formated_name = '-'.join(newlist[node_index].split(' ')[1:])
        update_name_of_branch = branch_name + '_' + formated_name
        for child in all_children:
            lists_combined += TrainingDataGenerator.find_intents(child, update_name_of_branch, treedict, newlist)
        return lists_combined

    @staticmethod
    def generate_question(paragraph):
        question_list = QuestionGenerator.generate(paragraph)
        return [paragraph, question_list]

    @staticmethod
    def generate_intent(treedict, newlist):
        value_out = TrainingDataGenerator.find_intents(0, 'root', treedict, newlist)
        helper_list = TrainingDataGenerator.helper_intent(0, 'root', treedict, newlist)
        training_data = []
        for i, element in enumerate(helper_list):
            key = value_out[i][0]
            value = value_out[i][1]
            train_examples = [sentence for sentence in value[1]]
            if element[1][0:3] == '<p>':
                training_data.append({
                    "intent": key,
                    "response": value[0],
                    "training_examples": train_examples
                })
        return training_data
