import os
from collections import defaultdict
from typing import Optional, Dict, Text

from loguru import logger
from rasa.core.training.story_conflict import find_story_conflicts
from rasa.shared.constants import UTTER_PREFIX
from rasa.shared.core.domain import Domain
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.generator import TrainingDataGenerator
from rasa.shared.core.training_data.structures import StoryStep, RuleStep
from rasa.shared.exceptions import YamlSyntaxException
from rasa.shared.importers.importer import TrainingDataImporter
from rasa.shared.importers.rasa import RasaFileImporter
from rasa.shared.nlu import constants
from rasa.shared.utils.validation import YamlValidationException
from rasa.validator import Validator

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import FormValidationAction, SlotSetAction, JiraAction, GoogleSearchAction, \
    ZendeskAction, EmailActionConfig, HttpActionConfig, PipedriveLeadsAction, PromptAction
from kairon.shared.actions.models import ActionType, ActionParameterType
from kairon.shared.constants import DEFAULT_ACTIONS, DEFAULT_INTENTS, SYSTEM_TRIGGERED_UTTERANCES, SLOT_SET_TYPE
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK
from kairon.shared.data.data_objects import MultiflowStories
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import StoryStepType
from kairon.shared.utils import Utility, StoryValidator


class TrainingDataValidator(Validator):
    """
    Tool to verify usage of intents, utterances,
    training examples and conflicts in stories.
    """

    def __init__(self, validator: Validator):
        """Initiate class with rasa validator object."""

        super().__init__(validator.domain, validator.intents, validator.story_graph, validator.nlu_config.as_dict())
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
            cls.actions = Utility.read_yaml(os.path.join(root_dir, 'actions.yml'))
            chat_client_config = Utility.read_yaml(os.path.join(root_dir, 'chat_client_config.yml'))
            cls.chat_client_config = chat_client_config if chat_client_config else {}
            multiflow_stories = Utility.read_yaml(os.path.join(root_dir, 'multiflow_stories.yml'))
            cls.multiflow_stories = multiflow_stories if multiflow_stories else {}
            cls.multiflow_stories_graph = StoryValidator.create_multiflow_story_graphs(multiflow_stories)

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

        for story_intent in all_intents:
            if story_intent not in self.domain.intents and story_intent not in DEFAULT_INTENTS:
                msg = f"The intent '{story_intent}' is used in your stories, but it is not listed in " \
                      f"the domain file. You should add it to your domain file!"
                if raise_exception:
                    raise AppException(msg)
                intents_mismatched.append(msg)

        unused_intents = set(self.domain.intents) - all_intents - set(DEFAULT_INTENTS)

        for intent in sorted(unused_intents):
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
        self.verify_utterances(raise_exception)

        utterance_actions = self.validator._gather_utterance_actions()
        user_actions = set(self.domain.user_actions)
        all_utterances_with_actions = user_actions.union(utterance_actions)
        fallback_action = DataUtility.parse_fallback_action(self.config)
        system_triggered_actions = DEFAULT_ACTIONS.union(SYSTEM_TRIGGERED_UTTERANCES).union(KAIRON_TWO_STAGE_FALLBACK)
        stories_utterances = set()
        multiflow_utterance = set()
        if self.multiflow_stories:
            multiflow_stories_utterances = StoryValidator.get_step_name_for_multiflow_stories(
                self.multiflow_stories_graph, "BOT")
            multiflow_stories_actions = {
                StoryStepType.http_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'HTTP_ACTION'),
                StoryStepType.email_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'EMAIL_ACTION'),
                StoryStepType.google_search_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'GOOGLE_SEARCH_ACTION'),
                StoryStepType.slot_set_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'SLOT_SET_ACTION'),
                StoryStepType.jira_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'JIRA_ACTION'),
                StoryStepType.form_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'FORM_ACTION'),
                StoryStepType.zendesk_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'ZENDESK_ACTION'),
                StoryStepType.pipedrive_leads_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'PIPEDRIVE_LEADS_ACTION'),
                StoryStepType.hubspot_forms_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'HUBSPOT_FORMS_ACTION'),
                StoryStepType.two_stage_fallback_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'TWO_STAGE_FALLBACK_ACTION'),
                StoryStepType.razorpay_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'RAZORPAY_ACTION'),
                StoryStepType.prompt_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'PROMPT_ACTION'),
                StoryStepType.web_search_action.value: StoryValidator.get_step_name_for_multiflow_stories(
                    self.multiflow_stories_graph, 'WEB_SEARCH_ACTION'),
            }
            multiflow_utterance = set(multiflow_stories_utterances.union(
                value for values in multiflow_stories_actions.values() for value in values))

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

        form_utterances = set()
        for form, form_data in self.domain.forms.items():
            for slot in form_data.get('required_slots', {}):
                form_utterances.add(f"utter_ask_{form}_{slot}")
        utterance_actions = utterance_actions.difference(form_utterances)

        for utterance in multiflow_utterance:
            if utterance not in all_utterances_with_actions:
                msg = f"The action '{utterance}' is used in multiflow stories but not listed in domain. You should add it to your domain file"
                if raise_exception:
                    raise AppException(msg)
                utterance_mismatch_summary.append(msg)

        unused_utterances = set(utterance_actions) - stories_utterances - multiflow_utterance - system_triggered_actions.union(fallback_action)

        for utterance in sorted(unused_utterances):
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
                        component_cfg in ["custom.ner.SpacyPatternNER", "custom.fallback.FallbackIntentFilter",
                                          "kairon.shared.nlu.featurizer.lm_featurizer.LanguageModelFeaturizer"] or
                        component_cfg in [custom_component for custom_component in Utility.environment['model']['pipeline']['custom']]):
                    config_errors.append("Invalid component " + component_cfg)
        else:
            config_errors.append("You didn't define any pipeline")

        if config.get('policies'):
            core_policies = DataUtility.get_rasa_core_policies()
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
    def verify_multiflow_story_structure(multiflow_story: list):
        story_error = []
        story_present = set()

        required_fields = {k for k, v in MultiflowStories._fields.items() if v and
                           k not in {'bot', 'user', 'timestamp', 'status', 'id'}}
        for story in multiflow_story:
            if isinstance(story, dict):
                if len(required_fields.difference(set(story.keys()))) > 0:
                    story_error.append(f'Required fields {required_fields} not found in story: {story.get("name")}')
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
        count = {'multiflow_stories': 0}
        if not isinstance(multiflow_stories, dict):
            story_errors = {'multiflow_story': ['Invalid multiflow story configuration format. Dictionary expected.']}
            return story_errors
        if multiflow_stories['multiflow_story'] or [] or None:
            count['multiflow_stories'] = len(multiflow_stories['multiflow_story'])
            errors = TrainingDataValidator.verify_multiflow_story_structure(multiflow_stories['multiflow_story'])
        return errors, count

    def validate_multiflow(self, raise_exception: bool = True):
        """
        Validates multiflow_stories.yml.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        if self.multiflow_stories:
            multiflow_errors, component_count = TrainingDataValidator.validate_multiflow_stories(self.multiflow_stories)
            self.component_count['multiflow_stories'] = len(self.multiflow_stories)
            self.summary['multiflow_stories'] = multiflow_errors
            self.component_count.update(component_count)
            if multiflow_errors and raise_exception:
                raise AppException("Invalid multiflow_stories.yml. Check logs!")

    @staticmethod
    def validate_custom_actions(actions: Dict):
        """
        Validates different actions supported by kairon.
        @param actions: Action configurations.
        @return: Set this flag to false to prevent raising exceptions.
        """
        is_data_invalid = False
        component_count = {
            'http_actions': 0, 'slot_set_actions': 0, 'form_validation_actions': 0, 'email_actions': 0,
            'google_search_actions': 0, 'jira_actions': 0, 'zendesk_actions': 0, 'pipedrive_leads_actions': 0,
            'prompt_actions': 0
        }
        error_summary = {
            'http_actions': [], 'slot_set_actions': [], 'form_validation_actions': [], 'email_actions': [],
            'google_search_actions': [], 'jira_actions': [], 'zendesk_actions': [], 'pipedrive_leads_actions': [],
            'prompt_actions': []
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
                'prompt_actions': ['Invalid action configuration format. Dictionary expected.']
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
                errors = TrainingDataValidator.__validate_prompt_actions(actions_list)
                is_data_invalid = True if errors else False
                error_summary['prompt_actions'] = errors
                component_count['prompt_actions'] = len(actions_list)

        return is_data_invalid, error_summary, component_count

    @staticmethod
    def __validate_slot_set_actions(slot_set_actions: list):
        """
        Validates slot set actions.
        @param slot_set_actions: Slot set actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in SlotSetAction._fields.items() if v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
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

        required_fields = {k for k, v in FormValidationAction._fields.items() if v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
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
                    if action['slot_set'].get('type') == 'current' and not Utility.check_empty_string(action['slot_set'].get('value')):
                        data_error.append('slot_set with type current should not have any value!')
                    if action['slot_set'].get('type') == 'slot' and Utility.check_empty_string(action['slot_set'].get('value')):
                        data_error.append('slot_set with type slot should have a valid slot value!')
                    if action['slot_set'].get('type') not in ['current', 'custom', 'slot']:
                        data_error.append('Invalid slot_set type!')
                else:
                    data_error.append('slot_set must be present')
                if f"{action['name']}_{action['slot']}" in actions_present:
                    data_error.append(f"Duplicate form validation action found for slot {action['slot']}: {action['name']}")
                actions_present.add(f"{action['name']}_{action['slot']}")
            else:
                data_error.append('Invalid action configuration format. Dictionary expected.')

        return data_error

    @staticmethod
    def __validate_prompt_actions(prompt_actions: list):
        """
        Validates form validation actions.
        @param form_actions: Form validation actions.
        """
        data_error = []
        actions_present = set()

        required_fields = {k for k, v in PromptAction._fields.items() if
                           v.required and k not in {'bot', 'user', 'timestamp', 'status'}}
        for action in prompt_actions:
            if isinstance(action, dict):
                if len(required_fields.difference(set(action.keys()))) > 0:
                    data_error.append(f'Required fields {required_fields} not found in action: {action.get("name")}')
                    continue
                if action.get('num_bot_responses') and (action['num_bot_responses'] > 5 or not isinstance(action['num_bot_responses'], int)):
                    data_error.append(f'num_bot_responses should not be greater than 5 and of type int: {action.get("name")}')
                if action.get('top_results') and (action['top_results'] > 30 or not isinstance(action['top_results'], int)):
                    data_error.append(f'top_results should not be greater than 30 and of type int: {action.get("name")}')
                if action.get('similarity_threshold'):
                    if not (0.3 <= action['similarity_threshold'] <= 1) or not (isinstance(action['similarity_threshold'], float) or isinstance(action['similarity_threshold'], int)):
                        data_error.append(f'similarity_threshold should be within 0.3 and 1 and of type int or float: {action.get("name")}')
                llm_prompts_errors = TrainingDataValidator.__validate_llm_prompts(action['llm_prompts'])
                if action.get('hyperparameters') is not None:
                    llm_hyperparameters_errors = TrainingDataValidator.__validate_llm_prompts_hyperparamters(action.get('hyperparameters'))
                    data_error.extend(llm_hyperparameters_errors)
                data_error.extend(llm_prompts_errors)
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
        bot_content_prompt_count = 0
        for prompt in llm_prompts:
            if prompt.get('type') == 'system':
                system_prompt_count += 1
            elif prompt.get('source') == 'history':
                history_prompt_count += 1
            elif prompt.get('source') == 'bot_content':
                bot_content_prompt_count += 1
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
            if system_prompt_count > 1:
                error_list.append('Only one system prompt can be present')
            if system_prompt_count == 0:
                error_list.append('System prompt is required')
            if history_prompt_count > 1:
                error_list.append('Only one history source can be present')
            if bot_content_prompt_count > 1:
                error_list.append('Only one bot_content source can be present')
        return error_list

    @staticmethod
    def __validate_llm_prompts_hyperparamters(hyperparameters: dict):
        error_list = []
        for key, value in hyperparameters.items():
            if key == 'temperature' and not 0.0 <= value <= 2.0:
                error_list.append("Temperature must be between 0.0 and 2.0!")
            elif key == 'presence_penalty' and not -2.0 <= value <= 2.0:
                error_list.append("presence_penality must be between -2.0 and 2.0!")
            elif key == 'frequency_penalty' and not -2.0 <= value <= 2.0:
                error_list.append("frequency_penalty must be between -2.0 and 2.0!")
            elif key == 'top_p' and not 0.0 <= value <= 1.0:
                error_list.append("top_p must be between 0.0 and 1.0!")
            elif key == 'n' and not 1 <= value <= 5:
                error_list.append("n must be between 1 and 5!")
            elif key == 'max_tokens' and not 5 <= value <= 4096:
                error_list.append("max_tokens must be between 5 and 4096!")
            elif key == 'logit_bias' and not isinstance(value, dict):
                error_list.append("logit_bias must be a dictionary!")
            elif key == 'stop':
                if value and (not isinstance(value, (str, int, list)) or (isinstance(value, list) and len(value) > 4)):
                    error_list.append("Stop must be None, a string, an integer, or an array of 4 or fewer strings or integers.")
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
            domain.check_missing_templates()
        except Exception as e:
            raise AppException(f"Failed to load domain.yml. Error: '{e}'")

    def validate_actions(self, raise_exception: bool = True):
        """
        Validate different types of actions.
        @param raise_exception: Set this flag to false to prevent raising exceptions.
        @return:
        """
        is_data_invalid, summary, component_count = TrainingDataValidator.validate_custom_actions(self.actions)
        self.component_count.update(component_count)
        self.summary.update(summary)
        if not is_data_invalid and raise_exception:
            raise AppException("Invalid actions.yml. Check logs!")

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
            self.validate_actions(raise_exception)
            self.validate_config(raise_exception)
            self.validate_multiflow(raise_exception)
        except Exception as e:
            logger.error(str(e))
            raise AppException(e)
