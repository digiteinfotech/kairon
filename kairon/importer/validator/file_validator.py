import os
from collections import defaultdict
from typing import Optional, Dict, Text, List

from loguru import logger
from rasa.core.training.story_conflict import find_story_conflicts
from rasa.shared.constants import UTTER_PREFIX
from rasa.shared.core.domain import Domain
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.generator import TrainingDataGenerator
from rasa.shared.core.training_data.structures import StoryStep, RuleStep
from rasa.shared.exceptions import YamlSyntaxException
from rasa.shared.importers.importer import TrainingDataImporter
from rasa.shared.nlu import constants
from rasa.shared.utils.validation import YamlValidationException
from rasa.validator import Validator
from pykwalify.core import Core
from ruamel import yaml

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import FormValidationAction, SlotSetAction, JiraAction, GoogleSearchAction, \
    ZendeskAction, EmailActionConfig, HttpActionConfig, PipedriveLeadsAction, PromptAction, RazorpayAction, \
    PyscriptActionConfig, DatabaseAction
from kairon.shared.actions.models import ActionType, ActionParameterType, DbActionOperationType
from kairon.shared.cognition.data_objects import CognitionSchema
from kairon.shared.constants import DEFAULT_ACTIONS, DEFAULT_INTENTS, SYSTEM_TRIGGERED_UTTERANCES, SLOT_SET_TYPE, \
    EXCLUDED_INTENTS
from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK
from kairon.shared.data.data_objects import MultiflowStories
from kairon.shared.data.model_data_imporer import KRasaFileImporter
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import StoryStepType
from kairon.shared.utils import Utility, StoryValidator


DEFAULT_OTHER_COLLECTIONS_PATH = 'other_collections.yml'


class TrainingDataValidator(Validator):
    """
    Tool to verify usage of intents, utterances,
    training examples and conflicts in stories.
    """

    def __init__(self, validator: Validator):
        """Initiate class with rasa validator object."""

        super().__init__(validator.domain, validator.intents, validator.story_graph, validator.config)
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
        validator = Validator.from_importer(importer)
        cls.story_graph = validator.story_graph
        cls.domain = validator.domain
        cls.intents = validator.intents
        cls.config = importer.get_config()
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
            file_importer = KRasaFileImporter(
                domain_path=domain_path, training_data_paths=training_data_paths, config_file=config_path,
            )
            cls.actions = Utility.read_yaml(os.path.join(root_dir, 'actions.yml'))
            chat_client_config = Utility.read_yaml(os.path.join(root_dir, 'chat_client_config.yml'))
            cls.chat_client_config = chat_client_config if chat_client_config else {}
            multiflow_stories = Utility.read_yaml(os.path.join(root_dir, 'multiflow_stories.yml'))
            cls.multiflow_stories = multiflow_stories if multiflow_stories else {}
            cls.multiflow_stories_graph = StoryValidator.create_multiflow_story_graphs(multiflow_stories)
            bot_content = Utility.read_yaml(os.path.join(root_dir, 'bot_content.yml'))
            cls.bot_content = bot_content if bot_content else {}
            other_collections = Utility.read_yaml(os.path.join(root_dir, DEFAULT_OTHER_COLLECTIONS_PATH))
            cls.other_collections = other_collections if other_collections else {}

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
        domain_intents = set(self.domain.intents) - EXCLUDED_INTENTS

        for intent in domain_intents:
            if intent not in nlu_data_intents and intent not in DEFAULT_INTENTS:
                msg = f"The intent '{intent}' is listed in the domain file, but " \
                      f"is not found in the NLU training data."
                if raise_exception:
                    raise AppException(msg)
                intents_mismatch_summary.append(msg)

        for intent in nlu_data_intents:
            if intent not in domain_intents and intent not in DEFAULT_INTENTS:
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
        multiflow_stories_intent = set()

        stories_intents = {
            event.intent["name"]
            for story in self.story_graph.story_steps
            for event in story.events
            if isinstance(event, UserUttered)
        }
        if self.multiflow_stories:
            multiflow_stories_intent = StoryValidator.get_step_name_for_multiflow_stories(self.multiflow_stories_graph,
                                                                                          "INTENT")
        all_intents = stories_intents.union(multiflow_stories_intent)
        domain_intents = set(self.domain.intents) - EXCLUDED_INTENTS

        for story_intent in all_intents:
            if story_intent not in domain_intents and story_intent not in DEFAULT_INTENTS:
                msg = f"The intent '{story_intent}' is used in your stories, but it is not listed in " \
                      f"the domain file. You should add it to your domain file!"
                if raise_exception:
                    raise AppException(msg)
                intents_mismatched.append(msg)
        unused_intents = set(domain_intents) - all_intents - set(DEFAULT_INTENTS)

        for intent in unused_intents:
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
        actions = self.domain.action_names_or_texts
        utterance_templates = set(self.domain.responses)
        self.component_count['utterances'] = len(self.domain.responses)

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
        action_mismatch_summary = []
        self.verify_utterances(raise_exception)
        user_actions = set(self.domain.user_actions)
        utterance_in_domain = self.validator._gather_utterance_actions()
        fallback_action = DataUtility.parse_fallback_action(self.config)
        system_triggered_actions = DEFAULT_ACTIONS.union(SYSTEM_TRIGGERED_UTTERANCES).union(KAIRON_TWO_STAGE_FALLBACK)
        story_actions = set()
        stories_utterances = set()
        multiflow_utterance = set()
        multiflow_actions = set()
        if self.multiflow_stories:
            multiflow_utterance, multiflow_actions = self.verify_utterance_and_actions_in_multiflow_stories(
                raise_exception)

        for story in self.story_graph.story_steps:
            for event in story.events:
                if not isinstance(event, ActionExecuted):
                    continue
                if not event.action_name.startswith(UTTER_PREFIX):
                    if event.action_name != 'action_restart' and event.action_name != '...' and not event.action_name.startswith(
                            'intent'):
                        story_actions.add(event.action_name)
                    continue

                if event.action_name in stories_utterances:
                    # we already processed this one before, we only want to warn once
                    continue

                if event.action_name not in utterance_in_domain and event.action_name not in system_triggered_actions:
                    msg = f"The action '{event.action_name}' is used in the stories, " \
                          f"but is not a valid utterance action. Please make sure " \
                          f"the action is listed in your domain and there is a " \
                          f"template defined with its name."
                    if raise_exception:
                        raise AppException(msg)
                    story_utterance_not_found_in_domain.append(msg)
                stories_utterances.add(event.action_name)

        for action in story_actions - {name for name in self.domain.form_names}:
            if action not in user_actions:
                msg = f"The action '{action}' is a user defined action used in the stories. " \
                      f"Please make sure the action is listed in your domain file."
                if raise_exception:
                    raise AppException(msg)
                action_mismatch_summary.append(msg)

        form_utterances = set()
        for form, form_data in self.domain.forms.items():
            for slot in form_data.get('required_slots', {}):
                form_utterances.add(f"utter_ask_{form}_{slot}")

        unused_utterances = set(utterance_in_domain) - form_utterances.union(
            set(self.domain.form_names)) - stories_utterances - multiflow_utterance - system_triggered_actions.union(
            fallback_action)
        for utterance in unused_utterances:
            msg = f"The utterance '{utterance}' is not used in any story."
            if raise_exception:
                raise AppException(msg)
            utterance_mismatch_summary.append(msg)

        unused_actions = user_actions - utterance_in_domain - set(story_actions) - set(multiflow_actions) - {
            f'validate_{name}' for name in self.domain.form_names}

        parallel_actions = set()
        all_actions = self.actions
        if all_actions and 'parallel_action' in all_actions:
            for action in all_actions['parallel_action']:
                parallel_actions.update(action['actions'])

        unused_actions -= parallel_actions

        for action in unused_actions:
            if action not in system_triggered_actions.union(fallback_action):
                msg = f"The action '{action}' is not used in any story."
                if raise_exception:
                    raise AppException(msg)
                action_mismatch_summary.append(msg)

        if not self.summary.get('utterances'):
            self.summary['utterances'] = []
        self.summary['utterances'] = self.summary['utterances'] + utterance_mismatch_summary

        if not self.summary.get('stories'):
            self.summary['stories'] = []
        self.summary['stories'] = self.summary['stories'] + story_utterance_not_found_in_domain

        if not self.summary.get('user_actions'):
            self.summary['user_actions'] = []
        self.summary['user_actions'] = self.summary['user_actions'] + action_mismatch_summary

        story_actions = story_actions - {name for name in self.domain.form_names}
        if not self.component_count.get('user_actions'):
            self.component_count['user_actions'] = []
        self.component_count['user_actions'] = len(multiflow_actions) + len(story_actions)

    def verify_utterance_and_actions_in_multiflow_stories(self, raise_exception: bool = True):
        utterance_mismatch_summary = []
        action_not_found_in_domain = []
        user_actions = set(self.domain.user_actions)
        actions = []
        utterances = []
        for step_type in StoryStepType:
            events = StoryValidator.get_step_name_for_multiflow_stories(self.multiflow_stories_graph,
                                                                        step_type.value)
            if step_type == StoryStepType.bot.value:
                utterances = events
            elif step_type != StoryStepType.intent.value and step_type != StoryStepType.slot.value:
                actions.extend(events)
                if step_type == StoryStepType.form_action.value:
                    user_actions.update(event for event in events
                                        if event in self.domain.form_names and f"validate_{event}" in user_actions)

        for utterance in utterances:
            if utterance not in user_actions:
                msg = f"The action '{utterance}' is used in the multiflow_stories, " \
                      f"but is not a valid utterance action. Please make sure " \
                      f"the action is listed in your domain and there is a " \
                      f"template defined with its name."
                if raise_exception:
                    raise AppException(msg)
                utterance_mismatch_summary.append(msg)

        for action in actions:
            if action not in user_actions:
                msg = f"The action '{action}' is a user defined action used in the multiflow_stories, " \
                      f"Please make sure the action is listed in your domain file."
                if raise_exception:
                    raise AppException(msg)
                action_not_found_in_domain.append(msg)

        if not self.summary.get('utterances'):
            self.summary['utterances'] = []
        self.summary['utterances'] = self.summary['utterances'] + utterance_mismatch_summary
        self.summary['user_actions'] = action_not_found_in_domain
        return utterances, actions

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
        from rasa.engine.recipes.default_components import DEFAULT_COMPONENTS
        components = [item.__name__ for item in DEFAULT_COMPONENTS]
        components = list(set(components).difference(set(Utility.environment['core']['deprecated-components'])))
        if config.get('pipeline'):
            for item in config['pipeline']:
                component_cfg = item['name']
                if not (component_cfg in components or
                        component_cfg in Utility.environment['core']['components']):
                    config_errors.append("Invalid component " + component_cfg)
        else:
            config_errors.append("You didn't define any pipeline")

        if config.get('policies'):
            for policy in config['policies']:
                if not (policy['name'] in components or policy['name'] in Utility.environment['core']['policies']):
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
        domain_intents = set(self.domain.intents) - EXCLUDED_INTENTS
        self.component_count['domain'] = {}
        self.component_count['domain']['intents'] = len(domain_intents)
        self.component_count['domain']['utterances'] = len(self.domain.responses)
        self.component_count['domain']['actions'] = len(self.domain.user_actions)
        self.component_count['domain']['forms'] = len(self.domain.form_names)
        self.component_count['domain']['slots'] = len(self.domain.slots)
        self.component_count['domain']['entities'] = len(self.domain.entities)
        self.component_count['utterances'] = len(self.domain.responses)
        if self.domain.is_empty():
            self.summary['domain'] = ["domain.yml is empty!"]

    @staticmethod
    def verify_multiflow_story_structure(multiflow_story: list):
        story_error = []
        story_present = set()

        required_fields = {k for k, v in MultiflowStories._fields.items() if v.required and
                           k not in {'bot', 'user', 'timestamp', 'status', 'id'}}
        for story in multiflow_story:
            if isinstance(story, dict):
                if len(required_fields.difference(set(story.keys()))) > 0:
                    story_error.append(
                        f'Required fields {required_fields} not found in story: {story.get("block_name")}')
                    continue
                if story.get('events'):
                    errors = StoryValidator.validate_multiflow_story_steps_file_validator(story.get('events'),
                                                                                          story.get('metadata', []))
                    story_error.extend(errors)
                if story['block_name'] in story_present:
                    story_error.append(f'Duplicate story found: {story["block_name"]}')
                story_present.add(story["block_name"])
            else:
                story_error.append('Invalid story configuration format. Dictionary expected.')
        return story_error

    @staticmethod
    def validate_multiflow_stories(multiflow_stories: Dict):
        errors = None
        count = 0
        if not isinstance(multiflow_stories, dict):
            story_errors = {'multiflow_story': ['Invalid multiflow story configuration format. Dictionary expected.']}
            return story_errors
        if multiflow_stories['multiflow_story']:
            errors = TrainingDataValidator.verify_multiflow_story_structure(multiflow_stories['multiflow_story'])
            count = len(multiflow_stories['multiflow_story'])
        return errors, count

    def validate_multiflow(self, raise_exception: bool = True):
        """
        Validates multiflow_stories.yml.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        if self.multiflow_stories:
            errors, count = TrainingDataValidator.validate_multiflow_stories(self.multiflow_stories)
            self.component_count['multiflow_stories'] = count
            self.summary['multiflow_stories'] = errors
            if errors and raise_exception:
                raise AppException("Invalid multiflow_stories.yml. Check logs!")

    #TODO: Depricated not needed anymore
    @staticmethod
    def validate_custom_actions(actions: Dict, bot: Text = None):
        """
        Validates different actions supported by kairon.
        @param actions: Action configurations.
        @param bot: bot id
        @return: Set this flag to false to prevent raising exceptions.
        """
        is_data_invalid = False
        component_count = {
            'http_actions': 0, 'slot_set_actions': 0, 'form_validation_actions': 0, 'email_actions': 0,
            'google_search_actions': 0, 'jira_actions': 0, 'zendesk_actions': 0, 'pipedrive_leads_actions': 0,
            'prompt_actions': 0, 'razorpay_actions': 0, 'pyscript_actions': 0
        }
        error_summary = {
            'http_actions': [], 'slot_set_actions': [], 'form_validation_actions': [], 'email_actions': [],
            'google_search_actions': [], 'jira_actions': [], 'zendesk_actions': [], 'pipedrive_leads_actions': [],
            'prompt_actions': [], 'razorpay_actions': [], 'pyscript_actions': []
        }
        if not actions:
            return True, error_summary, component_count
        if not isinstance(actions, dict):
            error_summary = {
                'http_actions': ['Invalid action configuration format. Dictionary expected.'],
                'slot_set_actions': ['Invalid action configuration format. Dictionary expected.'],
                'form_validation_actions': ['Invalid action configuration format. Dictionary expected.'],
                'email_actions': ['Invalid action configuration format. Dictionary expected.'],
                'google_search_actions': ['Invalid action configuration format. Dictionary expected.'],
                'jira_actions': ['Invalid action configuration format. Dictionary expected.'],
                'zendesk_actions': ['Invalid action configuration format. Dictionary expected.'],
                'pipedrive_leads_actions': ['Invalid action configuration format. Dictionary expected.'],
                'prompt_actions': ['Invalid action configuration format. Dictionary expected.'],
                'razorpay_actions': ['Invalid action configuration format. Dictionary expected.'],
                'pyscript_actions': ['Invalid action configuration format. Dictionary expected.']
            }
            return False, error_summary, component_count
        for action_type, actions_list in actions.items():
            if action_type == ActionType.http_action.value and actions_list:
                errors = TrainingDataValidator.__validate_http_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['http_actions'] = errors
                component_count['http_actions'] = len(actions_list)
            elif action_type == ActionType.slot_set_action.value and actions_list:
                errors = TrainingDataValidator.__validate_slot_set_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['slot_set_actions'] = errors
                component_count['slot_set_actions'] = len(actions_list)
            elif action_type == ActionType.form_validation_action.value and actions_list:
                errors = TrainingDataValidator.__validate_form_validation_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['form_validation_actions'] = errors
                component_count['form_validation_actions'] = len(actions_list)
            elif action_type == ActionType.email_action.value and actions_list:
                errors = TrainingDataValidator.__validate_email_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['email_actions'] = errors
                component_count['email_actions'] = len(actions_list)
            elif action_type == ActionType.google_search_action.value and actions_list:
                errors = TrainingDataValidator.__validate_google_search_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['google_search_actions'] = errors
                component_count['google_search_actions'] = len(actions_list)
            elif action_type == ActionType.jira_action.value and actions_list:
                errors = TrainingDataValidator.__validate_jira_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['jira_actions'] = errors
                component_count['jira_actions'] = len(actions_list)
            elif action_type == ActionType.zendesk_action.value and actions_list:
                errors = TrainingDataValidator.__validate_zendesk_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['zendesk_actions'] = errors
                component_count['zendesk_actions'] = len(actions_list)
            elif action_type == ActionType.pipedrive_leads_action.value and actions_list:
                errors = TrainingDataValidator.__validate_pipedrive_leads_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['pipedrive_leads_actions'] = errors
                component_count['pipedrive_leads_actions'] = len(actions_list)
            elif action_type == ActionType.prompt_action.value and actions_list:
                errors = TrainingDataValidator.__validate_prompt_actions(actions_list, bot)
                is_data_invalid = True if errors else False
                error_summary['prompt_actions'] = errors
                component_count['prompt_actions'] = len(actions_list)
            elif action_type == ActionType.razorpay_action.value and actions_list:
                errors = TrainingDataValidator.__validate_razorpay_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['razorpay_actions'] = errors
                component_count['razorpay_actions'] = len(actions_list)
            elif action_type == ActionType.pyscript_action.value and actions_list:
                errors = TrainingDataValidator.__validate_pyscript_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['pyscript_actions'] = errors
                component_count['pyscript_actions'] = len(actions_list)
            elif action_type == ActionType.database_action.value and actions_list:
                errors = TrainingDataValidator.__validate_database_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['database_actions'] = errors
                component_count['database_actions'] = len(actions_list)
        return is_data_invalid, error_summary, component_count

    @staticmethod
    def __validate_slot_set_actions(slot_set_actions: list):
        """
        Validates slot set actions.
        @param slot_set_actions: Slot set actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in SlotSetAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in slot_set_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if not isinstance(action.get('set_slots'), list):
                    data_error.append(f'Invalid field set_slots: {action.get("name")}. List expected.')
                    continue
                for slot in action.get('set_slots'):
                    if slot.get('type') not in {s_type.value for s_type in SLOT_SET_TYPE}:
                        data_error.append(f'Invalid slot type {slot.get("type")}: {action["name"]}')
                    if Utility.check_empty_string(slot.get('name')):
                        data_error.append(f'Slot name cannot be empty: {action["name"]}')
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_form_validation_actions(form_actions: list):
        """
        Validates form validation actions.
        @param form_actions: Form validation actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in FormValidationAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in form_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found in action: {action.get("name")}')
                    continue
                if action.get('validation_semantic') and not isinstance(action['validation_semantic'], str):
                    data_error.append(f'Invalid validation semantic: {action["name"]}')
                if action.get('slot_set'):
                    if Utility.check_empty_string(action['slot_set'].get('type')):
                        data_error.append('slot_set should have type current as default!')
                    if action['slot_set'].get('type') == 'current' and not Utility.check_empty_string(
                            action['slot_set'].get('value')):
                        data_error.append('slot_set with type current should not have any value!')
                    if action['slot_set'].get('type') == 'slot' and Utility.check_empty_string(
                            action['slot_set'].get('value')):
                        data_error.append('slot_set with type slot should have a valid slot value!')
                    if action['slot_set'].get('type') not in ['current', 'custom', 'slot']:
                        data_error.append('Invalid slot_set type!')
                else:
                    data_error.append('slot_set must be present')
                if f"{action['name']}_{action['slot']}" in actions_present:
                    data_error.append(
                        f"Duplicate form validation action found for slot {action['slot']}: {action['name']}")
                actions_present.add(f"{action['name']}_{action['slot']}")
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_prompt_actions(prompt_actions: list, bot: Text = None):
        """
        Validates prompt actions.
        @param prompt_actions: Promptactions.
        @param bot: bot id
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in PromptAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in prompt_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(
                        f'Required fields {sorted(required_fields)} not found in action: {action.get("name")}')
                    continue
                if action.get('num_bot_responses') and (
                        action['num_bot_responses'] > 5 or not isinstance(action['num_bot_responses'], int)):
                    data_error.append(
                        f'num_bot_responses should not be greater than 5 and of type int: {action.get("name")}')
                llm_prompts_errors = TrainingDataValidator.__validate_llm_prompts(action['llm_prompts'])
                if action.get('hyperparameters'):
                    llm_hyperparameters_errors = TrainingDataValidator.__validate_llm_prompts_hyperparameters(
                        action.get('hyperparameters'), action.get("llm_type", "openai"), bot)
                    data_error.extend(llm_hyperparameters_errors)
                data_error.extend(llm_prompts_errors)
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')
        return data_error

    @staticmethod
    def __validate_database_actions(database_actions: list):
        data_error = []
        actions_present = set()
        required_fields = {k for k, v in DatabaseAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in database_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {list(required_fields)} not found: {action.get("name")}')
                    continue
                for idx, item in enumerate(action.get('payload', [])):
                    if not item.get('query_type') or not item.get('type') or not item.get('value'):
                        data_error.append(f"Payload {idx} must contain fields 'query_type', 'type' and 'value'!")
                    if item.get('query_type') not in [qtype.value for qtype in DbActionOperationType]:
                        data_error.append(f"Unknown query_type found: {item['query_type']} in payload {idx}")
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')
        return data_error

    @staticmethod
    def __validate_llm_prompts(llm_prompts: dict):
        error_list = []
        system_prompt_count = 0
        history_prompt_count = 0
        for prompt in llm_prompts:
            if prompt.get('hyperparameters') is not None:
                hyperparameters = prompt.get('hyperparameters')
                for key, value in hyperparameters.items():
                    if key == 'similarity_threshold':
                        if not (0.3 <= value <= 1.0) or not (
                                isinstance(value, float) or isinstance(value, int)):
                            error_list.append(
                                f"similarity_threshold should be within 0.3 and 1.0 and of type int or float!")
                    if key == 'top_results' and (value > 30 or not isinstance(value, int)):
                        error_list.append("top_results should not be greater than 30 and of type int!")

            if prompt.get('type') == 'system':
                system_prompt_count += 1
            elif prompt.get('source') == 'history':
                history_prompt_count += 1
            if prompt.get('type') not in ['user', 'system', 'query']:
                error_list.append('Invalid prompt type')
            if prompt.get('source') not in ['static', 'slot', 'action', 'history', 'bot_content']:
                error_list.append('Invalid prompt source')
            if prompt.get('type') and not isinstance(prompt.get('type'), str):
                error_list.append('type in LLM Prompts should be of type string.')
            if prompt.get('source') and not isinstance(prompt.get('source'), str):
                error_list.append('source in LLM Prompts should be of type string.')
            if prompt.get('instructions') and not isinstance(prompt.get('instructions'), str):
                error_list.append('Instructions in LLM Prompts should be of type string.')
            if prompt.get('type') == 'system' and prompt.get('source') != 'static':
                error_list.append('System prompt must have static source')
            if prompt.get('type') == 'query' and prompt.get('source') != 'static':
                error_list.append('Query prompt must have static source')
            if not prompt.get('data') and prompt.get('source') == 'action':
                error_list.append('Data must contain action name')
            if not prompt.get('data') and prompt.get('source') == 'slot':
                error_list.append('Data must contain slot name')
            if Utility.check_empty_string(prompt.get('name')):
                error_list.append('Name cannot be empty')
            if prompt.get('data') and not isinstance(prompt.get('data'), str):
                error_list.append('data field in prompts should of type string.')
            if not prompt.get('data') and prompt.get('source') == 'static':
                error_list.append('data is required for static prompts')
            if prompt.get('source') == 'bot_content' and Utility.check_empty_string(prompt.get('data')):
                error_list.append("Collection is required for bot content prompts!")
            if system_prompt_count > 1:
                error_list.append('Only one system prompt can be present')
            if system_prompt_count == 0:
                error_list.append('System prompt is required')
            if history_prompt_count > 1:
                error_list.append('Only one history source can be present')
        return error_list

    @staticmethod
    def __validate_llm_prompts_hyperparameters(hyperparameters: dict, llm_type: str, bot: str = None):
        error_list = []
        try:
            Utility.validate_llm_hyperparameters(hyperparameters, llm_type, bot, AppException)
        except AppException as e:
            error_list.append(e.__str__())
        return error_list

    @staticmethod
    def __validate_jira_actions(jira_actions: list):
        """
        Validates jira actions.
        @param jira_actions: Jira actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in JiraAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in jira_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['issue_type'] == 'Subtask' and not action.get('parent_key'):
                    data_error.append(f'parent_key is required for issue_type Subtask: {action["name"]}')
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_google_search_actions(google_actions: list):
        """
        Validates Google search actions.
        @param google_actions: Google search actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in GoogleSearchAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in google_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                try:
                    if action.get("num_results"):
                        int(action["num_results"])
                except ValueError:
                    data_error.append(f'int value required for num_results in action: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_zendesk_actions(zendesk_actions: list):
        """
        Validates Zendesk actions.
        @param zendesk_actions: Zendesk actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in ZendeskAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in zendesk_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_pipedrive_leads_actions(pipedrive_actions: list):
        """
        Validates Zendesk actions.
        @param zendesk_actions: Zendesk actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in PipedriveLeadsAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in pipedrive_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                if not (isinstance(action['metadata'], dict) and action['metadata'].get('name')):
                    data_error.append(f'Invalid metadata. "name" is required: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_email_actions(email_actions: list):
        """
        Validates Email actions.
        @param email_actions: Email actions.
        """
        data_error = []
        actions_present = set()
        required_fields = {k for k, v in EmailActionConfig._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in email_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("action_name")}')
                    continue
                if action['action_name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["action_name"]}')
                actions_present.add(action["action_name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_razorpay_actions(razorpay_actions: list):
        """
        Validates razorpay actions.
        @param razorpay_actions: Razorpay actions.
        """
        data_error = []
        actions_present = set()
        required_fields = {k for k, v in RazorpayAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in razorpay_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_pyscript_actions(pyscript_actions: list):
        """
        Validates pyscript actions.
        @param pyscript_actions: Pyscript actions.
        """
        data_error = []
        actions_present = set()
        required_fields = {k for k, v in PyscriptActionConfig._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in pyscript_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found: {action.get("name")}')
                    continue
                if action['name'] in actions_present:
                    data_error.append(f'Duplicate action found: {action["name"]}')
                actions_present.add(action["name"])
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_http_actions(http_actions: Dict):
        """
        Validates http actions.
        @param http_actions: Http actions as dict.
        """
        required_fields = {k for k, v in HttpActionConfig._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        action_present = set()
        data_error = []
        action_param_types = {a_type.value for a_type in ActionParameterType}

        for http_obj in http_actions:
            if all(name in http_obj for name in required_fields):
                if (not http_obj.get('request_method') or
                        http_obj.get('request_method').upper() not in {"POST", "PUT", "GET", "DELETE"}):
                    data_error.append('Invalid request method: ' + http_obj['action_name'])

                if http_obj['action_name'] in action_present:
                    data_error.append("Duplicate http action found: " + http_obj['action_name'])
                action_present.add(http_obj['action_name'])

                if http_obj.get('params_list'):
                    for param in http_obj.get('params_list'):
                        if not param.get('key'):
                            data_error.append('Invalid params_list for http action: ' + http_obj['action_name'])
                            continue
                        if param.get('parameter_type') not in action_param_types:
                            data_error.append('Invalid params_list for http action: ' + http_obj['action_name'])
                            continue
                        if param.get('parameter_type') == 'slot' and not param.get('value'):
                            param['value'] = param.get('key')

                if http_obj.get('headers'):
                    for param in http_obj.get('headers'):
                        if not param.get('key'):
                            data_error.append('Invalid headers for http action: ' + http_obj['action_name'])
                            continue
                        if param.get('parameter_type') not in action_param_types:
                            data_error.append('Invalid headers for http action: ' + http_obj['action_name'])
                            continue
                        if param.get('parameter_type') == 'slot' and not param.get('value'):
                            param['value'] = param.get('key')
            else:
                data_error.append(f"Required http action fields {required_fields} not found")
        return data_error

    @staticmethod
    def validate_domain(domain_path: Text):
        try:
            domain = Domain.load(domain_path)
            domain.check_missing_responses()
        except Exception as e:
            raise AppException(f"Failed to load domain.yml. Error: '{e}'")

    def validate_actions(self, bot: Text = None, raise_exception: bool = True):
        """
        Validate different types of actions.
        @param bot: bot id
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        is_data_valid, summary, component_count = ActionSerializer.validate(bot, self.actions, self.other_collections)
        self.component_count.update(component_count)
        self.summary.update(summary)
        if not is_data_valid and raise_exception:
            raise AppException("Invalid actions.yml. Check logs!")

    @staticmethod
    def validate_content(bot: Text, user: Text, bot_content: List, save_data: bool = False,
                         overwrite: bool = True):

        bot_content_errors = []

        settings = MongoProcessor.get_bot_settings(bot, user)
        if not settings.to_mongo().to_dict()['llm_settings'].get('enable_faq'):
            bot_content_errors.append("Please enable GPT on bot before uploading")

        current_dir = os.path.dirname(os.path.realpath(__file__))
        bot_content_schema_file_path = os.path.join(current_dir, "bot_content_schema.yaml")
        schema_validator = Core(source_data=bot_content, schema_files=[bot_content_schema_file_path])

        from kairon.shared.cognition.processor import CognitionDataProcessor
        new_collection_names = [data_item.get('collection') for data_item in bot_content]
        if CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, new_collection_names, overwrite):
            bot_content_errors.append('Collection limit exceeded!')

        try:
            schema_validator.validate(raise_exception=True)
            logger.info("Validation successful!")
        except Exception as e:
            logger.info(f"Validation failed: {e}")
            bot_content_errors.append(f"Invalid bot_content.yml. Content does not match required schema: {e}")

        if save_data and not overwrite:
            for item in bot_content:
                if item.get('type') == 'json':
                    collection_name = item.get('collection')
                    existing_schema = CognitionSchema.objects(bot=bot, collection_name=collection_name).first()
                    if existing_schema:
                        existing_metadata = existing_schema.metadata
                        uploaded_metadata = item.get('metadata')
                        if len(existing_metadata) == len(uploaded_metadata):
                            for existing_meta, uploaded_meta in zip(existing_metadata, uploaded_metadata):
                                if existing_meta.column_name != uploaded_meta['column_name'] or \
                                        existing_meta.create_embeddings != uploaded_meta['create_embeddings'] or \
                                        existing_meta.data_type != uploaded_meta['data_type'] or \
                                        existing_meta.enable_search != uploaded_meta['enable_search']:
                                    bot_content_errors.append("Invalid bot_content.yml. Collection with same name and "
                                                              "different metadata cannot be uploaded")
                                    break
                        else:
                            bot_content_errors.append("Invalid bot_content.yml. Collection with same name and "
                                                      "different metadata cannot be uploaded")

        return bot_content_errors

    def validate_bot_content(self, bot: Text, user: Text, save_data: bool = True,
                             overwrite: bool = True, raise_exception: bool = True):
        """
        Validates bot_content.yml.
        :param bot: bot id
        :param user: user id
        :param save_data: flag to save data
        :param overwrite: flag to overwrite data
        :param raise_exception: Set this flag to false to prevent raising exceptions.
        :return:
        """
        if self.bot_content:
            errors = TrainingDataValidator.validate_content(bot, user, self.bot_content, save_data, overwrite)
            self.summary['bot_content'] = errors
            if errors and raise_exception:
                raise AppException("Invalid bot_content.yml. Check logs!")

    @staticmethod
    def validate_rules(rules_path: str):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        schema_file_path = os.path.join(current_dir, "..", "shared", "schemas", "rules.yml")

        with open(schema_file_path, 'r') as schema_file:
            schema = yaml.safe_load(schema_file)

        validator = Validator(schema)

        with open(rules_path, 'r') as rules_file:
            rules = yaml.safe_load(rules_file)

        if not validator.validate(rules):
            raise ValueError(f"Validation errors: {validator.errors}")

    def validate_training_data(self, raise_exception: bool = True, bot: Text = None, user: Text = None,
                               save_data: bool = True,
                               overwrite: bool = True):
        """
        Validate training data.
        :param raise_exception: Set this flag to false to prevent raising exceptions.
        :param bot: bot id
        :param user: user id
        :param save_data: flag to save data
        :param overwrite: flag to overwrite data
        :return:
        """
        try:
            self.verify_story_structure(raise_exception)
            self.verify_domain_validity()
            self.verify_nlu(raise_exception)
            self.validate_actions(bot, raise_exception)
            self.validate_config(raise_exception)
            self.validate_multiflow(raise_exception)
            self.validate_bot_content(bot, user, save_data, overwrite, raise_exception)

        except Exception as e:
            logger.error(str(e))
            raise AppException(e)
