import ruamel.yaml
from rasa.shared.core.training_data.story_reader.story_step_builder import StoryStepBuilder
from rasa.shared.utils import io, validation
from rasa.shared.utils.io import write_yaml
from ruamel.yaml import YAML
from collections import OrderedDict
from typing import Text, Any, Union, List, Optional, Dict
from pathlib import Path

from rasa.shared.core.constants import RULE_SNIPPET_ACTION_NAME
from rasa.shared.core.events import ActionExecuted
from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
from rasa.shared.core.training_data.structures import StoryStep, Checkpoint, STORY_START, RuleStep, StoryGraph
from rasa.shared.importers.rasa import Domain
from rasa.shared.importers.rasa import RasaFileImporter
from rasa.shared.core.training_data.story_reader.yaml_story_reader import YAMLStoryReader, KEY_RULE_NAME, \
    KEY_RULE_CONDITION, KEY_RULE_FOR_CONVERSATION_START, KEY_STEPS, KEY_WAIT_FOR_USER_INPUT_AFTER_RULE, KEY_STORIES, \
    KEY_USER_INTENT, KEY_USER_MESSAGE, KEY_OR, KEY_ACTION, KEY_BOT_END_TO_END_MESSAGE, KEY_CHECKPOINT, KEY_SLOT_NAME, \
    KEY_ACTIVE_LOOP, KEY_METADATA, KEY_RULES, StoryParser, RuleParser

from kairon.shared.models import FlowTagType





class CustomRuleStep(RuleStep):
    def __init__(self, flow_tags: Optional[List[str]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flow_tags = flow_tags if flow_tags is not None else [FlowTagType.chatbot_flow.value]


class CustomStoryStepBuilder(StoryStepBuilder):
    def __init__(
        self, flow_tags = None, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.flow_tags = flow_tags if flow_tags else [FlowTagType.chatbot_flow.value]

    def _next_story_steps(self) -> List[StoryStep]:
        start_checkpoints = self._prev_end_checkpoints()
        if not start_checkpoints:
            start_checkpoints = [Checkpoint(STORY_START)]
        step_class = CustomRuleStep if self.is_rule else StoryStep
        current_turns = [
            step_class(
                block_name=self.name,
                start_checkpoints=start_checkpoints,
                source_name=self.source_name,
                flow_tags=self.flow_tags,
            )
        ]
        return current_turns



class KRuleParser(RuleParser):

    def _new_part(self, item_name: Text, item: Dict[Text, Any]) -> None:
        flow_tags = item.get("metadata", {}).get("flow_tags", [])
        self._new_rule_part(item_name, self.source_name, flow_tags)
        conditions = item.get(KEY_RULE_CONDITION, [])
        self._parse_rule_conditions(conditions)
        if not item.get(KEY_RULE_FOR_CONVERSATION_START):
            self._parse_rule_snippet_action()

    def _new_rule_part(self, name: Text, source_name: Optional[Text], flow_tags = None) -> None:
        self._add_current_stories_to_result()
        self.current_step_builder = CustomStoryStepBuilder(flow_tags, name, source_name, is_rule=True)



class CustomStoryGraph(StoryGraph):
    def __init__(self, story_steps: List[StoryStep]):
        super().__init__(story_steps)
        self.custom_story_steps = story_steps
        self.flow_tags = []
        for step in story_steps:
            if hasattr(step, "flow_tags"):
                self.flow_tags.extend(step.flow_tags)
        print("CustomStoryGraph created with flow_tags:", self.flow_tags)

class KYAMLStoryReader(YAMLStoryReader):
    """Parses metadata to attach flow_tags."""

    def _new_step_builder(self) -> StoryStep:
        if self.source_name.endswith("rules.yml"):
            return CustomRuleStep()
        else:
            return RuleStep()

    def _parse_step(self, step: Union[Text, Dict[Text, Any]]) -> None:
        if isinstance(step, str):
            io.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"Found an unexpected step in the {self._get_item_title()} "
                f"description:\n{step}\nThe step is of type `str` "
                f"which is only allowed for the rule snippet action "
                f"'{RULE_SNIPPET_ACTION_NAME}'. It will be skipped.",
                docs=self._get_docs_link(),
            )
        elif KEY_USER_INTENT in step.keys() or KEY_USER_MESSAGE in step.keys():
            self._parse_user_utterance(step)
        elif KEY_OR in step.keys():
            self._parse_or_statement(step)
        elif KEY_ACTION in step.keys():
            self._parse_action(step)
        elif KEY_BOT_END_TO_END_MESSAGE in step.keys():
            self._parse_bot_message(step)
        elif KEY_CHECKPOINT in step.keys():
            self._parse_checkpoint(step)
        elif KEY_SLOT_NAME in step.keys():
            self._parse_slot(step)
        elif KEY_ACTIVE_LOOP in step.keys():
            self._parse_active_loop(step[KEY_ACTIVE_LOOP])
        elif KEY_METADATA in step.keys():
            self._parse_metadata(step)
        else:
            io.raise_warning(
                f"Issue found in '{self.source_name}':\n"
                f"Found an unexpected step in the {self._get_item_title()} "
                f"description:\n{step}\nIt will be skipped.",
                docs=self._get_docs_link(),
            )

    def _parse_metadata(self, step: Dict[Text, Any]) -> None:
        flow_tags = step.get("metadata", {}).get("flow_tags", [])
        self.current_step_builder.flow_tags = flow_tags


    def read_from_parsed_yaml(
        self, parsed_content: Dict[Text, Union[Dict, List]]
    ) -> List[StoryStep]:
        """Read stories from parsed YAML.

        Args:
            parsed_content: The parsed YAML as a dictionary.

        Returns:
            The parsed stories or rules.
        """
        if not validation.validate_training_data_format_version(
            parsed_content, self.source_name
        ):
            return []

        for key, parser_class in {
            KEY_STORIES: StoryParser,
            KEY_RULES: KRuleParser,
        }.items():
            data = parsed_content.get(key) or []
            parser = parser_class.from_reader(self)
            parser.parse_data(data)
            self.story_steps.extend(parser.get_steps())

        return self.story_steps


class KRasaFileImporter(RasaFileImporter):
    def get_stories(self, exclusion_percentage: Optional[int] = None) -> CustomStoryGraph:
        story_graph = self._get_stories(exclusion_percentage)
        return CustomStoryGraph(story_graph.story_steps)

    def _get_stories(self, exclusion_percentage: Optional[int] = None) -> CustomStoryGraph:
        return CustomStoryGraph(self.load_data_from_files(
            self._story_files, self.get_domain(), exclusion_percentage
        ))

    @staticmethod
    def load_data_from_files(
        story_files: List[Text], domain: Domain, exclusion_percentage: Optional[int] = None
    ) -> List[StoryStep]:
        story_steps = []
        for story_file in story_files:
            reader = KYAMLStoryReader(domain, story_file)
            steps = reader.read_from_file(story_file)
            story_steps.extend(steps)
        if exclusion_percentage and exclusion_percentage != 100:
            import random
            idx = int(round(exclusion_percentage / 100.0 * len(story_steps)))
            random.shuffle(story_steps)
            story_steps = story_steps[:-idx]
        return story_steps



class KYAMLStoryWriter(YAMLStoryWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.yaml = YAML()
        self.yaml.representer.add_representer(list, self.represent_list)

    def represent_list(self, dumper, data):
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data)

    def process_rule_step(self, rule_step: RuleStep) -> OrderedDict:
        """Converts a RuleStep into an ordered dict.

        Args:
            rule_step: RuleStep object.

        Returns:
            Converted rule step.
        """
        result: OrderedDict[Text, Any] = OrderedDict()
        result[KEY_RULE_NAME] = rule_step.block_name

        condition_steps = []
        condition_events = rule_step.get_rules_condition()
        for event in condition_events:
            processed = self.process_event(event)
            if processed:
                condition_steps.append(processed)
        if condition_steps:
            result[KEY_RULE_CONDITION] = condition_steps

        normal_events = rule_step.get_rules_events()
        if normal_events and not (
            isinstance(normal_events[0], ActionExecuted)
            and normal_events[0].action_name
            == RULE_SNIPPET_ACTION_NAME
        ):
            result[KEY_RULE_FOR_CONVERSATION_START] = True

        normal_steps = []
        for event in normal_events:
            processed = self.process_event(event)
            if processed:
                normal_steps.append(processed)
        if normal_steps:
            result[KEY_STEPS] = normal_steps

        if len(normal_events) > 1:
            last_event = normal_events[len(normal_events) - 1]
            if (
                isinstance(last_event, ActionExecuted)
                and last_event.action_name
                == RULE_SNIPPET_ACTION_NAME
            ):
                result[KEY_WAIT_FOR_USER_INPUT_AFTER_RULE] = False

        if hasattr(rule_step, "flow_tags"):
            result["metadata"] = {"flow_tags": [str(tag) for tag in rule_step.flow_tags]}

        return result

    def dump(
            self,
            target: Union[Text, Path, ruamel.yaml.compat.StringIO],
            story_steps: List[StoryStep],
            is_appendable: bool = False,
            is_test_story: bool = False,
    ) -> None:
        """Writes Story steps into a target file/stream.

        Args:
            target: name of the target file/stream to write the YAML to.
            story_steps: Original story steps to be converted to the YAML.
            is_appendable: Specify if result should not contain
                           high level keys/definitions and can be appended to
                           the existing story file.
            is_test_story: Identifies if the stories should be exported in test stories
                           format.
        """
        result = self.stories_to_yaml(story_steps, is_test_story)
        if is_appendable and KEY_STORIES in result:
            result = result[KEY_STORIES]

        write_yaml(result, target, True)




