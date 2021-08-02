import os
from collections import defaultdict
from typing import Optional, Dict

from loguru import logger
from rasa.core.training.story_conflict import find_story_conflicts
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.generator import TrainingDataGenerator
from rasa.shared.core.training_data.structures import StoryStep, RuleStep
from rasa.shared.importers.rasa import RasaFileImporter
from rasa.shared.constants import UTTER_PREFIX
from rasa.validator import Validator
from rasa.shared.exceptions import YamlSyntaxException
from rasa.shared.importers.importer import TrainingDataImporter
from rasa.shared.nlu import constants
from rasa.shared.utils.validation import YamlValidationException

from kairon.shared.constants import DEFAULT_ACTIONS, DEFAULT_INTENTS, SYSTEM_TRIGGERED_UTTERANCES
from kairon.utils import Utility
from kairon.exceptions import AppException


class TrainingDataValidator(Validator):
    """
    Tool to verify usage of intents, utterances,
    training examples and conflicts in stories.
    """

    def __init__(self, validator: Validator):
        """Initiate class with rasa validator object."""

        super().__init__(validator.domain, validator.intents, validator.story_graph)
        self.validator = validator
        self.summary = {}
        self.component_count = {}

    @classmethod
    async def from_importer(cls, importer: TrainingDataImporter):
        """
        Create validator from importer.
        @param importer: rasa training data importer object.
        @return: validator
        """
        validator = await Validator.from_importer(importer)
        cls.story_graph = validator.story_graph
        cls.domain = validator.domain
        cls.intents = validator.intents
        cls.config = await importer.get_config()
        return cls(validator)

    @classmethod
    async def from_training_files(cls, training_data_paths: str, domain_path: str, config_path: str, root_dir):
        """
        Create validator from training files.
        @param training_data_paths: nlu.yml file path.
        @param domain_path: domain.yml file path.
        @param config_path: config.yml file path.
        @param root_dir: training data root directory.
        @return:
        """
        if not (os.path.exists(training_data_paths) and os.path.exists(domain_path) and os.path.exists(config_path)):
            raise AppException("Some training files are absent!")
        try:
            file_importer = RasaFileImporter(
                domain_path=domain_path, training_data_paths=training_data_paths, config_file=config_path,
            )
            cls.http_actions = Utility.read_yaml(os.path.join(root_dir, 'http_action.yml'))

            return await TrainingDataValidator.from_importer(file_importer)
        except YamlValidationException as e:
            exc = Utility.replace_file_name(str(e), root_dir)
            raise AppException(exc)
        except YamlSyntaxException as e:
            exc = Utility.replace_file_name(str(e), root_dir)
            raise AppException(exc)
        except Exception as e:
            raise AppException(e)

    def verify_example_repetition_in_intents(self, raise_exception: bool = True):
        """
        Finds repeating training examples.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        duplicate_training_example = []
        duplication_hash = defaultdict(set)
        self.component_count['training_examples'] = len(self.intents.intent_examples)
        for example in self.intents.intent_examples:
            text = example.get(constants.TEXT)
            duplication_hash[text].add(example.get("intent"))

        for text, intents in duplication_hash.items():

            if len(duplication_hash[text]) > 1:
                intents_string = ", ".join(sorted(intents))
                msg = f"The example '{text}' was found labeled with multiple different intents " \
                      f"in the training data. Each annotated message should only appear with one " \
                      f"intent. You should fix that conflict The example is labeled with: {intents_string}."
                if raise_exception:
                    raise AppException(msg)
                duplicate_training_example.append(msg)
        self.summary['training_examples'] = duplicate_training_example

    def verify_story_structure(self, raise_exception: bool = True, max_history: Optional[int] = None):
        """
        Validates whether the bot behaviour in stories is deterministic.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @param max_history:
        @return:
        """
        self.component_count['stories'] = 0
        self.component_count['rules'] = 0
        for steps in self.story_graph.story_steps:
            if isinstance(steps, RuleStep):
                self.component_count['rules'] += 1
            elif isinstance(steps, StoryStep):
                self.component_count['stories'] += 1

        trackers = TrainingDataGenerator(
            self.story_graph,
            domain=self.domain,
            remove_duplicates=False,
            augmentation_factor=0,
        ).generate_story_trackers()

        conflicts = find_story_conflicts(
            trackers, self.domain, max_history
        )

        if conflicts:
            conflict_msg = []
            for conflict in conflicts:
                conflict_msg.append(str(conflict))
                if raise_exception:
                    raise AppException(str(conflict))
            self.summary['stories'] = conflict_msg

    def verify_intents(self, raise_exception: bool = True):
        """
        Validated intents in nlu.yml.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        intents_mismatch_summary = []
        nlu_data_intents = {e.data["intent"] for e in self.intents.intent_examples}
        self.component_count['intents'] = len(nlu_data_intents)

        for intent in self.domain.intents:
            if intent not in nlu_data_intents and intent not in DEFAULT_INTENTS:
                msg = f"The intent '{intent}' is listed in the domain file, but " \
                      f"is not found in the NLU training data."
                if raise_exception:
                    raise AppException(msg)
                intents_mismatch_summary.append(msg)

        for intent in nlu_data_intents:
            if intent not in self.domain.intents and intent not in DEFAULT_INTENTS:
                msg = f"There is a message in the training data labeled with intent '{intent}'." \
                      f" This intent is not listed in your domain."
                if raise_exception:
                    raise AppException(msg)
                intents_mismatch_summary.append(msg)
        self.summary['intents'] = intents_mismatch_summary

    def verify_intents_in_stories(self, raise_exception: bool = True):
        """
        Validates intents in stories.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        intents_mismatched = []
        self.verify_intents(raise_exception)

        stories_intents = {
            event.intent["name"]
            for story in self.story_graph.story_steps
            for event in story.events
            if isinstance(event, UserUttered)
        }

        for story_intent in stories_intents:
            if story_intent not in self.domain.intents and story_intent not in DEFAULT_INTENTS:
                msg = f"The intent '{story_intent}' is used in your stories, but it is not listed in " \
                      f"the domain file. You should add it to your domain file!"
                if raise_exception:
                    raise AppException(msg)
                intents_mismatched.append(msg)

        for intent in self.domain.intents:
            if intent not in stories_intents and intent not in DEFAULT_INTENTS:
                msg = f"The intent '{intent}' is not used in any story."
                if raise_exception:
                    raise AppException(msg)
                intents_mismatched.append(msg)

        if not self.summary.get('intents'):
            self.summary['intents'] = []
        self.summary['intents'] = self.summary['intents'] + intents_mismatched

    def verify_utterances(self, raise_exception: bool = True):
        """
        Validated utterances in domain.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        utterance_mismatch_summary = []
        actions = self.domain.action_names
        utterance_templates = set(self.domain.templates)
        self.component_count['utterances'] = len(self.domain.templates)

        for utterance in utterance_templates:
            if utterance not in actions:
                msg = f"The utterance '{utterance}' is not listed under 'actions' in the domain file." \
                      f" It can only be used as a template."
                if raise_exception:
                    raise AppException(msg)
                utterance_mismatch_summary.append(msg)

        for action in actions:
            if action.startswith(UTTER_PREFIX):
                if action not in utterance_templates:
                    msg = f"There is no template for the utterance action '{action}'. " \
                          f"The action is listed in your domains action list, but there is no " \
                          f"template defined with this name. You should add a template with this key."
                    if raise_exception:
                        raise AppException(msg)
                    utterance_mismatch_summary.append(msg)

        self.summary['utterances'] = utterance_mismatch_summary

    def verify_utterances_in_stories(self, raise_exception: bool = True):
        """
        Validates utterances in stories.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        utterance_mismatch_summary = []
        story_utterance_not_found_in_domain = []
        self.validator.verify_utterances()

        utterance_actions = self.validator._gather_utterance_actions()
        fallback_action = Utility.parse_fallback_action(self.config)
        system_triggered_actions = DEFAULT_ACTIONS.union(SYSTEM_TRIGGERED_UTTERANCES)
        stories_utterances = set()

        for story in self.story_graph.story_steps:
            for event in story.events:
                if not isinstance(event, ActionExecuted):
                    continue
                if not event.action_name.startswith(UTTER_PREFIX):
                    # we are only interested in utter actions
                    continue

                if event.action_name in stories_utterances:
                    # we already processed this one before, we only want to warn once
                    continue

                if event.action_name not in utterance_actions and event.action_name not in system_triggered_actions:
                    msg = f"The action '{event.action_name}' is used in the stories, " \
                          f"but is not a valid utterance action. Please make sure " \
                          f"the action is listed in your domain and there is a " \
                          f"template defined with its name."
                    if raise_exception:
                        raise AppException(msg)
                    story_utterance_not_found_in_domain.append(msg)
                stories_utterances.add(event.action_name)

        for utterance in utterance_actions:
            if utterance not in stories_utterances and utterance not in system_triggered_actions.union(fallback_action):
                msg = f"The utterance '{utterance}' is not used in any story."
                if raise_exception:
                    raise AppException(msg)
                utterance_mismatch_summary.append(msg)

        if not self.summary.get('utterances'):
            self.summary['utterances'] = []
        self.summary['utterances'] = self.summary['utterances'] + utterance_mismatch_summary

        if not self.summary.get('stories'):
            self.summary['stories'] = []
        self.summary['stories'] = self.summary['stories'] + story_utterance_not_found_in_domain

    def verify_nlu(self, raise_exception: bool = True):
        """
        Validates nlu data.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        self.verify_intents_in_stories(raise_exception)
        self.verify_example_repetition_in_intents(raise_exception)
        self.verify_utterances_in_stories(raise_exception)

    @staticmethod
    def validate_rasa_config(config: Dict):
        """
        validates bot config.yml content for invalid entries

        :param config: configuration
        :return: None
        """
        config_errors = []
        from rasa.nlu.registry import registered_components as nlu_components
        if config.get('pipeline'):
            for item in config['pipeline']:
                component_cfg = item['name']
                if not (component_cfg in nlu_components or
                        component_cfg in ["custom.ner.SpacyPatternNER", "custom.fallback.FallbackIntentFilter"]):
                    config_errors.append("Invalid component " + component_cfg)
        else:
            config_errors.append("You didn't define any pipeline")

        if config.get('policies'):
            core_policies = Utility.get_rasa_core_policies()
            for policy in config['policies']:
                if policy['name'] not in core_policies:
                    config_errors.append("Invalid policy " + policy['name'])
        else:
            config_errors.append("You didn't define any policies")
        return config_errors

    def validate_config(self, raise_exception: bool = True):
        """
        Validates config.yml.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        config_errors = TrainingDataValidator.validate_rasa_config(self.config)
        self.summary['config'] = config_errors
        if config_errors and raise_exception:
            raise AppException("Invalid config.yml. Check logs!")

    def verify_domain_validity(self):
        """
        Checks whether domain is empty or not.
        @return:
        """
        self.component_count['domain'] = {}
        self.component_count['domain']['intents'] = len(self.domain.intents)
        self.component_count['domain']['utterances'] = len(self.domain.templates)
        self.component_count['domain']['actions'] = len(self.domain.user_actions)
        self.component_count['domain']['forms'] = len(self.domain.form_names)
        self.component_count['domain']['slots'] = len(self.domain.slots)
        self.component_count['domain']['entities'] = len(self.domain.entities)
        self.component_count['utterances'] = len(self.domain.templates)
        if self.domain.is_empty():
            self.summary['domain'] = ["domain.yml is empty!"]

    @staticmethod
    def validate_http_actions(http_actions: Dict):
        """
        Validates http actions.
        @param http_actions: Http actions as dict.
        @return: Set this flag to false to prevent raising exceptions.
        """
        required_fields = ['action_name', 'response', 'http_url', 'request_method']
        action_names = []
        data_error = []

        if not http_actions or not http_actions.get('http_actions'):
            return

        actions = http_actions.get('http_actions')
        for http_obj in actions:
            if all(name in http_obj for name in required_fields):
                if (not http_obj.get('request_method') or
                        http_obj.get('request_method').upper() not in {"POST", "GET", "DELETE"}):
                    data_error.append('Invalid request method: ' + http_obj['action_name'])

                if http_obj['action_name'] not in action_names:

                    if http_obj.get('params_list'):
                        for param in http_obj.get('params_list'):
                            if not param.get('key'):
                                data_error.append('Invalid params_list for http action: ' + http_obj['action_name'])
                                continue
                            if param.get('parameter_type') not in {'slot', 'value', 'sender_id'}:
                                data_error.append('Invalid params_list for http action: ' + http_obj['action_name'])
                                continue
                            if param.get('parameter_type') == 'slot' and not param.get('value'):
                                param['value'] = param.get('key')

                    action_names.append(http_obj['action_name'])
                else:
                    data_error.append("Duplicate http action found: " + http_obj['action_name'])
            else:
                data_error.append("Required http action fields not found")
        return data_error

    def validate_custom_actions(self, raise_exception: bool = True):
        """
        Validate http actions.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        self.component_count['http_actions'] = len(self.http_actions.get('http_actions')) \
            if self.http_actions and self.http_actions.get('http_actions') else 0
        errors = TrainingDataValidator.validate_http_actions(self.http_actions)
        self.summary['http_actions'] = errors
        if errors and raise_exception:
            raise AppException("Invalid http_actions.yml. Check logs!")

    def validate_training_data(self, raise_exception: bool = True):
        """
        Validate training data.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        try:
            self.verify_story_structure(raise_exception)
            self.verify_domain_validity()
            self.verify_nlu(raise_exception)
            self.validate_custom_actions(raise_exception)
            self.validate_config(raise_exception)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)
