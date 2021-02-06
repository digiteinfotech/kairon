'''
Custom component to get fallback action intent
Reference: https://forum.rasa.com/t/fallback-intents-for-context-sensitive-fallbacks/963
'''

from rasa.nlu.classifiers.classifier import IntentClassifier

class FallbackIntentFilter(IntentClassifier):

    # Name of the component to be used when integrating it in a
    # pipeline. E.g. ``[ComponentA, ComponentB]``
    # will be a proper pipeline definition where ``ComponentA``
    # is the name of the first component of the pipeline.
    name = "FallbackIntentFilter"

    # Defines what attributes the pipeline component will
    # provide when called. The listed attributes
    # should be set by the component on the message object
    # during test and train, e.g.
    # ```message.set("entities", [...])```
    provides = []

    # Which attributes on a message are required by this
    # component. e.g. if requires contains "tokens", than a
    # previous component in the pipeline needs to have "tokens"
    # within the above described `provides` property.
    requires = []

    # Defines the default configuration parameters of a component
    # these values can be overwritten in the pipeline configuration
    # of the model. The component should choose sensible defaults
    # and should be able to create reasonable results with the defaults.
    defaults = {}

    # Defines what language(s) this component can handle.
    # This attribute is designed for instance method: `can_handle_language`.
    # Default value is None which means it can handle all languages.
    # This is an important feature for backwards compatibility of components.
    language_list = None

    def __init__(self, component_config=None, low_threshold=0.3, high_threshold=0.4, fallback_intent="fallback",
                 out_of_scope_intent="out_of_scope"):
        super().__init__(component_config)
        self.fb_low_threshold = low_threshold
        self.fb_high_threshold = high_threshold
        self.fallback_intent = fallback_intent
        self.out_of_scope_intent = out_of_scope_intent

    def process(self, message, **kwargs):
        message_confidence = message.data['intent']['confidence']
        new_intent = None
        if message_confidence <= self.fb_low_threshold:
            new_intent = {'name': self.out_of_scope_intent, 'confidence': message_confidence}
        elif message_confidence <= self.fb_high_threshold:
            new_intent = {'name': self.fallback_intent, 'confidence': message_confidence}
        if new_intent is not None:
            message.data['intent'] = new_intent
            message.data['intent_ranking'].insert(0, new_intent)
