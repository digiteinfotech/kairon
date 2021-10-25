import os
from typing import Dict, Text, Optional, Set

from rasa.exceptions import ModelNotFound
from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter

from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor


class ModelTester:
    """
    Class to run tests on a trained model.

    """

    @staticmethod
    async def run_tests_on_model(bot: str, run_e2e: bool = False):
        """
        Runs tests on a trained model.

        Args:
            bot: bot id for which test is run.
            run_e2e: if True, test is initiated on test stories and nlu data.

        Returns: dictionary with evaluation results
        """
        from kairon import Utility

        bot_home = os.path.join('testing_data', bot)
        try:
            model_path = Utility.get_latest_model(bot)
            Utility.make_dirs(bot_home)
            processor = MongoProcessor()
            nlu = processor.load_nlu(bot)
            nlu_path = os.path.join(bot_home, "nlu.yml")
            nlu_as_str = nlu.nlu_as_yaml().encode()
            Utility.write_to_file(nlu_path, nlu_as_str)

            stories = processor.load_stories(bot)
            stories_path = os.path.join(bot_home, "stories.yml")
            YAMLStoryWriter().dump(stories_path, stories.story_steps)

            stories_results = await ModelTester.run_test_on_stories(stories_path, model_path, run_e2e)
            nlu_results = ModelTester.run_test_on_nlu(nlu_path, model_path)
            return nlu_results, stories_results
        except ModelNotFound:
            raise AppException("Could not find any model. Please train a model before running tests.")
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
        from rasa.test import get_evaluation_metrics
        from rasa.core.test import _create_data_generator, _collect_story_predictions
        from rasa.core.agent import Agent

        agent = Agent.load(model_path)

        generator = await _create_data_generator(stories_path, agent, use_e2e=e2e)
        completed_trackers = generator.generate_story_trackers()

        story_evaluation, _ = await _collect_story_predictions(
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
            failed_stories_summary.append(events_tracker)

        for story in story_evaluation.successful_stories:
            events_tracker = []
            for event in story.events:
                events_tracker.append(vars(event))
            success_stories_summary.append(events_tracker)
        return {
            "report": report,
            "precision": precision,
            "f1": f1,
            "accuracy": accuracy,
            "actions": story_evaluation.action_list,
            "in_training_data_fraction": story_evaluation.in_training_data_fraction,
            "is_end_to_end_evaluation": e2e,
            "failed_stories": failed_stories_summary,
            "successful_stories": success_stories_summary
        }

    @staticmethod
    def run_test_on_nlu(nlu_path: str, model_path: str):
        """
        Run tests on stories.

        Args:
            nlu_path: path where nlu test data is present as YAML.
            model_path: Model path where model on which test has to be run is present.

        Returns: dictionary with evaluation results
        """
        from rasa.model import get_model
        import rasa.shared.nlu.training_data.loading
        from rasa.nlu.model import Interpreter
        from rasa.nlu.test import (
            remove_pretrained_extractors,
            get_eval_data,
            evaluate_intents,
            evaluate_response_selections,
            get_entity_extractors,
        )

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
            for r in intent_results:
                if r.intent_target == r.intent_prediction:
                    successes.append({
                        "text": r.message,
                        "intent": r.intent_target,
                        "intent_prediction": {
                            'name': r.intent_prediction,
                            "confidence": r.confidence,
                        },
                    })
                else:
                    errors.append({
                        "text": r.message,
                        "intent": r.intent_target,
                        "intent_prediction": {
                            'name': r.intent_prediction,
                            "confidence": r.confidence,
                        },
                    })
            result["intent_evaluation"]['successes'] = successes
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
            result["response_selection_evaluation"]['successes'] = successes
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
        from rasa.test import get_evaluation_metrics
        from rasa.nlu.test import (
            NO_ENTITY,
            align_all_entity_predictions,
            merge_labels,
            substitute_labels,
            collect_successful_entity_predictions,
            collect_incorrect_entity_predictions
        )

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

            report, precision, f1, accuracy = get_evaluation_metrics(
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
                "report": report,
                "precision": precision,
                "f1_score": f1,
                "accuracy": accuracy,
                'successes': successes,
                'errors': errors
            }

        return result
