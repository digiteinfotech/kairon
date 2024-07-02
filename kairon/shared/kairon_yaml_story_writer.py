from typing import List, Text, Any, Union
from collections import OrderedDict

from rasa.shared.core.training_data.story_writer.yaml_story_writer import YAMLStoryWriter
from rasa.shared.core.training_data.structures import StoryStep
from rasa.shared.core.events import Event


from rasa.shared.core.training_data.story_reader.yaml_story_reader import KEY_STORY_NAME, KEY_STEPS


class kaironYAMLStoryWriter(YAMLStoryWriter):
    """Custom YAML Story Writer with overridden _filter_event function."""

    def process_story_step(self, story_step: StoryStep) -> OrderedDict:
        """Converts a single story step into an ordered dict with a custom filter."""
        result: OrderedDict[Text, Any] = OrderedDict()
        result[KEY_STORY_NAME] = story_step.block_name
        steps = self.process_checkpoints(story_step.start_checkpoints)
        for event in story_step.events:
            if not self._filter_event(event):  # Use custom filter event
                continue
            processed = self.process_event(event)
            if processed:
                steps.append(processed)

        steps.extend(self.process_checkpoints(story_step.end_checkpoints))

        result[KEY_STEPS] = steps

        return result

    @staticmethod
    def _filter_event(event: Union["Event", List["Event"]]) -> bool:
        """Identifies if the event should be converted/written.

        Args:
            event: target event to check.

        Returns:
            `True` if the event should be converted/written, `False` otherwise.
        """
        if isinstance(event, list):
            return True

        return (
            not StoryStep.is_action_unlikely_intent(event)
            and not StoryStep.is_action_session_start(event)
        )