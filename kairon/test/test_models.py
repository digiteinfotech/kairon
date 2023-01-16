import asyncio
import os
import random
from typing import Dict, Text, Optional, Set

from loguru import logger
from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
from rasa.shared.nlu.constants import TEXT
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.nlu.test import (
            NO_ENTITY,
            align_all_entity_predictions,
            merge_labels,
            substitute_labels,
            collect_successful_entity_predictions,
            collect_incorrect_entity_predictions,
            remove_pretrained_extractors,
            get_eval_data,
            evaluate_intents,
            evaluate_response_selections,
            get_entity_extractors,
        )
from rasa.model_testing import get_evaluation_metrics

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.constant import TRAINING_EXAMPLE
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility


class ModelTester:
    """
    Class to run tests on a trained model.

    """

    @staticmethod
    def run_tests_on_model(bot: str, run_e2e: bool = False, augment_data: bool = True):
        """
        Runs tests on a trained model.

        Args:
            bot: bot id for which test is run.
            run_e2e: if True, test is initiated on test stories and nlu data.
            augment_data: whether training phrases should be augmented.

        Returns: dictionary with evaluation results
        """
        from kairon.shared.utils import Utility

        bot_home = os.path.join('testing_data', bot)
        logger.info(f"model test data path: {bot_home}")
        try:
            model_path = Utility.get_latest_model(bot)
            nlu_path, stories_path, saved_phrases = TestDataGenerator.create(bot, run_e2e, augment_data)
            stories_results = asyncio.run(ModelTester.run_test_on_stories(stories_path, model_path, run_e2e))
            nlu_results = ModelTester.run_test_on_nlu(nlu_path, model_path, saved_phrases)
            return nlu_results, stories_results
        except Exception as e:
            raise AppException(f'Model testing failed: {e}')
        finally:
            if os.path.exists(bot_home):
                Utility.delete_directory(bot_home)

    @staticmethod
    async def run_test_on_stories(stories_path: str, model_path: str, e2e: bool = False):
        """
        Run tests on stories.

        Args:
            stories_path: path where test stories are present as YAML.
            model_path: Model path where model on which test has to be run is present.
            e2e: if True, end to end test is initiated where intent prediction is also done along with action prediction.

        Returns: dictionary with evaluation results
        """
        from rasa.model_testing import get_evaluation_metrics
        from rasa.core.test import _create_data_generator, _collect_story_predictions
        from rasa.core.agent import Agent

        test_report = {}
        agent = Agent.load(model_path)

        generator = await _create_data_generator(stories_path, agent, use_conversation_test_files=e2e)
        completed_trackers = generator.generate_story_trackers()

        story_evaluation, _, _ = await _collect_story_predictions(
            completed_trackers, agent, use_e2e=e2e
        )
        targets, predictions = story_evaluation.evaluation_store.serialise()
        report, precision, f1, accuracy = get_evaluation_metrics(targets, predictions, output_dict=True)
        failed_stories_summary = []
        success_stories_summary = []
        for story in story_evaluation.failed_stories:
            events_tracker = []
            for event in story.events:
                events_tracker.append(vars(event))
            failed_stories_summary.append({'name': story.sender_id, 'events': events_tracker})

        for story in story_evaluation.successful_stories:
            events_tracker = []
            for event in story.events:
                events_tracker.append(vars(event))
            success_stories_summary.append({'name': story.sender_id, 'events': events_tracker})

        num_failed = len(story_evaluation.failed_stories)
        num_correct = len(story_evaluation.successful_stories)
        num_warnings = len(story_evaluation.stories_with_warnings)
        num_convs = num_failed + num_correct
        if num_convs and isinstance(report, Dict):
            conv_accuracy = num_correct / num_convs
            test_report["conversation_accuracy"] = {
                "accuracy": conv_accuracy,
                "success_count": num_correct,
                "failure_count": num_failed,
                "total_count": num_convs,
                "with_warnings": num_warnings,
            }

        test_report.update({
            # "report": report,
            "precision": precision,
            "f1": f1,
            "accuracy": accuracy,
            # "actions": story_evaluation.action_list,
            # "in_training_data_fraction": story_evaluation.in_training_data_fraction,
            # "is_end_to_end_evaluation": e2e,
            "failed_stories": failed_stories_summary,
            # "successful_stories": success_stories_summary,
        })
        return test_report

    @staticmethod
    def run_test_on_nlu(nlu_path: str, model_path: str, saved_phrases: set):
        """
        Run tests on stories.

        Args:
            nlu_path: path where nlu test data is present as YAML.
            model_path: Model path where model on which test has to be run is present.
            saved_phrases: Phrases that are present as part of the training examples in the bot.

        Returns: dictionary with evaluation results
        """
        from rasa.model import get_model
        import rasa.shared.nlu.training_data.loading
        from rasa.nlu.model import Interpreter

        unpacked_model = get_model(model_path)
        nlu_model = os.path.join(unpacked_model, "nlu")
        interpreter = Interpreter.load(nlu_model)
        interpreter.pipeline = remove_pretrained_extractors(interpreter.pipeline)
        test_data = rasa.shared.nlu.training_data.loading.load_data(
            nlu_path, interpreter.model_metadata.language
        )

        result: Dict[Text, Optional[Dict]] = {
            "intent_evaluation": None,
            "entity_evaluation": None,
            "response_selection_evaluation": None,
        }

        (intent_results, response_selection_results, entity_results) = get_eval_data(
            interpreter, test_data
        )

        if intent_results:
            successes = []
            errors = []
            result["intent_evaluation"] = evaluate_intents(intent_results, None, False, False, True)
            if result["intent_evaluation"].get('predictions'):
                del result["intent_evaluation"]['predictions']
                del result["intent_evaluation"]['report']
            for r in intent_results:
                is_synthesized = True
                if r.message in saved_phrases:
                    is_synthesized = False
                if r.intent_target == r.intent_prediction:
                    successes.append({
                        "text": r.message,
                        "is_synthesized": is_synthesized,
                        "intent": r.intent_target,
                        "intent_prediction": {
                            'name': r.intent_prediction,
                            "confidence": r.confidence,
                        },
                    })
                else:
                    errors.append({
                        "text": r.message,
                        "is_synthesized": is_synthesized,
                        "intent": r.intent_target,
                        "intent_prediction": {
                            'name': r.intent_prediction,
                            "confidence": r.confidence,
                        },
                    })
            result["intent_evaluation"]['total_count'] = len(successes) + len(errors)
            result["intent_evaluation"]['success_count'] = len(successes)
            result["intent_evaluation"]['failure_count'] = len(errors)
            result["intent_evaluation"]['successes'] = []
            result["intent_evaluation"]['errors'] = errors

        if response_selection_results:
            successes = []
            errors = []
            result["response_selection_evaluation"] = evaluate_response_selections(
                response_selection_results,
                None,
                False,
                False,
                True
            )
            if result["response_selection_evaluation"].get('predictions'):
                del result["response_selection_evaluation"]['predictions']
                del result["response_selection_evaluation"]['report']
            for r in response_selection_results:
                if r.intent_response_key_prediction == r.intent_response_key_target:
                    successes.append({
                        "text": r.message,
                        "intent_response_key_target": r.intent_response_key_target,
                        "intent_response_key_prediction": {
                            "name": r.intent_response_key_prediction,
                            "confidence": r.confidence,
                        },
                    })
                else:
                    if not Utility.check_empty_string(r.intent_response_key_target):
                        errors.append(
                            {
                                "text": r.message,
                                "intent_response_key_target": r.intent_response_key_target,
                                "intent_response_key_prediction": {
                                    "name": r.intent_response_key_prediction,
                                    "confidence": r.confidence,
                                },
                            }
                        )
            result["response_selection_evaluation"]['total_count'] = len(successes) + len(errors)
            result["response_selection_evaluation"]['success_count'] = len(successes)
            result["response_selection_evaluation"]['failure_count'] = len(errors)
            result["response_selection_evaluation"]['successes'] = []
            result["response_selection_evaluation"]['errors'] = errors

        if any(entity_results):
            extractors = get_entity_extractors(interpreter)
            result["entity_evaluation"] = ModelTester.__evaluate_entities(entity_results, extractors)
        return result

    @staticmethod
    def __evaluate_entities(entity_results, extractors: Set[Text]) -> Dict:
        """
        Creates summary statistics for each entity extractor.

        Logs precision, recall, and F1 per entity type for each extractor.

        Args:
            entity_results: entity evaluation results
            extractors: entity extractors to consider

        Returns: dictionary with evaluation results
        """
        aligned_predictions = align_all_entity_predictions(entity_results, extractors)
        merged_targets = merge_labels(aligned_predictions)
        from rasa.shared.nlu.constants import NO_ENTITY_TAG
        merged_targets = substitute_labels(merged_targets, NO_ENTITY_TAG, NO_ENTITY)

        result = {}

        for extractor in extractors:
            merged_predictions = merge_labels(aligned_predictions, extractor)
            merged_predictions = substitute_labels(
                merged_predictions, NO_ENTITY_TAG, NO_ENTITY
            )

            _, precision, f1, accuracy = get_evaluation_metrics(
                    merged_targets,
                    merged_predictions,
                    output_dict=False,
                    exclude_label=NO_ENTITY,
                )

            successes = collect_successful_entity_predictions(
                entity_results, merged_predictions, merged_targets
            )
            errors = collect_incorrect_entity_predictions(
                entity_results, merged_predictions, merged_targets
            )

            result[extractor] = {
                "total_count": len(successes) + len(errors),
                "success_count": len(successes),
                "failure_count": len(errors),
                "precision": precision,
                "f1_score": f1,
                "accuracy": accuracy,
                # 'successes': successes,
                'errors': errors
            }

        return result


class TestDataGenerator:

    @staticmethod
    def create(bot: str, use_test_stories: bool = False, augment_data: bool = True):
        messages = []
        saved_phrases = set()
        bot_home = os.path.join('testing_data', bot)
        Utility.make_dirs(bot_home)
        processor = MongoProcessor()
        intents_and_training_examples = processor.get_intents_and_training_examples(bot)
        for intent, phrases in intents_and_training_examples.items():
            if augment_data:
                aug_messages, original_input_text = TestDataGenerator.__prepare_nlu(intent, phrases)
            else:
                aug_messages = list(TestDataGenerator.__prepare_training_phrases(intent, phrases))
                original_input_text = phrases

            original_input_text = {text['text'] for text in original_input_text or []}
            messages.extend(aug_messages)
            saved_phrases.update(original_input_text)

        nlu_data = TrainingData(training_examples=messages)
        stories = processor.load_stories(bot)
        rules = processor.get_rules_for_training(bot)
        stories = stories.merge(rules)
        if stories.is_empty() or nlu_data.is_empty():
            raise AppException('Not enough training data exists. Please add some training data.')

        nlu_as_str = nlu_data.nlu_as_yaml().encode()
        nlu_path = os.path.join(bot_home, "nlu.yml")
        Utility.write_to_file(nlu_path, nlu_as_str)

        if use_test_stories:
            stories_path = os.path.join(bot_home, "test_stories.yml")
        else:
            stories_path = os.path.join(bot_home, "stories.yml")
        YAMLStoryWriter().dump(stories_path, stories.story_steps, is_test_story=use_test_stories)
        return nlu_path, stories_path, saved_phrases

    @staticmethod
    def augment_sentences(input_text: list):
        from kairon.shared.augmentation.utils import AugmentationUtils

        final_augmented_text = []
        all_input_text = []
        all_stop_words = []
        all_entities = []
        similarity_threshold = Utility.environment["model"]["test"]["augmentation_similarity_threshold"]
        for text in input_text or []:
            stopwords = []
            entity_names = []
            if text.get('entities'):
                stopwords = [entity['value'] for entity in text['entities']]
                entity_names = [entity['entity'] for entity in text['entities']]
            augmented_text = TestDataGenerator.__augment_sentences_with_mistakes_and_entities(text['text'], stopwords, entity_names)
            augmented_text = AugmentationUtils.get_similar(augmented_text, text['text'], similarity_threshold)
            final_augmented_text.extend(augmented_text)
            all_input_text.append(text['text'])
            if stopwords:
                all_stop_words.extend(stopwords)
            if entity_names:
                all_entities.extend(entity_names)

        if all_input_text:
            augmented_text = TestDataGenerator.fetch_augmented_text_in_batches(all_input_text)
            final_augmented_text.extend(
                TestDataGenerator.__augment_entities(augmented_text, list(all_stop_words), list(all_entities))
            )
            final_augmented_text.extend(augmented_text)
        return final_augmented_text

    @staticmethod
    def fetch_augmented_text_in_batches(text: list):
        from augmentation.paraphrase.paraphrasing import ParaPhrasing

        augmented_text = []

        for i in range(0, len(text), 10):
            augmented_text.extend(ParaPhrasing.paraphrases(text[i:i + 10]))

        return augmented_text

    @staticmethod
    def __augment_sentences_with_mistakes_and_entities(input_text: str, stopwords, entity_names):
        from kairon.shared.augmentation.utils import AugmentationUtils

        augmented_text = list(AugmentationUtils.augment_sentences_with_errors([input_text], stopwords))
        augmented_text.extend(
            TestDataGenerator.__augment_entities(augmented_text, stopwords, entity_names)
        )
        return augmented_text

    @staticmethod
    def __augment_entities(input_text: list, stopwords: list, entity_names: list):
        from kairon.shared.augmentation.utils import AugmentationUtils

        final_augmented_text = []

        if input_text and stopwords:
            for txt in input_text:
                for i, word in enumerate(stopwords):
                    if word in txt:
                        final_augmented_text.append(txt.replace(word, f'[{word}]({entity_names[i]})'))
                        final_augmented_text.extend(list(
                            map(
                                lambda synonym: txt.replace(word, f'[{synonym}]({entity_names[i]})'),
                                AugmentationUtils.generate_synonym(word))
                        ))
        return final_augmented_text

    @staticmethod
    def __prepare_nlu(intent: str, training_examples: list):
        if training_examples:
            test_data_threshold = Utility.environment['model']['test'].get('dataset_threshold') or 10

            if len(training_examples) >= 100:
                test_data_threshold = Utility.environment['model']['test'].get('dataset_percentage') or 10
                test_data_threshold = test_data_threshold/100
                num_samples = int(len(training_examples) * test_data_threshold)
                training_examples = random.sample(training_examples, num_samples)
            elif len(training_examples) > test_data_threshold:
                training_examples = random.sample(training_examples, test_data_threshold)

            phrases_to_augment = training_examples.copy()
            augmented_examples = TestDataGenerator.augment_sentences(phrases_to_augment)
            augmented_examples = list(TestDataGenerator.__prepare_training_phrases(intent, augmented_examples))
            aug_original_input_text = list(TestDataGenerator.__prepare_training_phrases(intent, phrases_to_augment))
            augmented_examples.extend(aug_original_input_text)
            return augmented_examples, training_examples
        else:
            return [], []

    @staticmethod
    def __prepare_training_phrases(intent: str, phrases: list):
        for phrase in phrases or []:
            yield TestDataGenerator.__prepare_msg(intent, phrase)
        if not phrases:
            return

    @staticmethod
    def __prepare_msg(intent: str, phrase):
        message = Message()
        if isinstance(phrase, str):
            plain_text, entities = DataUtility.extract_text_and_entities(phrase)
        else:
            plain_text, entities = phrase.get("text"), phrase.get("entities")
        message.data = {TRAINING_EXAMPLE.INTENT.value: intent, TEXT: plain_text}
        if entities:
            message.data[TRAINING_EXAMPLE.ENTITIES.value] = entities
        return message
