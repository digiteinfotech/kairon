import json
from typing import Text

from kairon.shared.end_user_metrics.constants import MetricTypes
from kairon.shared.end_user_metrics.data_objects import EndUserMetrics


class EndUserMetricsProcessor:
    """
    Data processor to add custom end user metrics.
    """

    @staticmethod
    def add_log(log_type: MetricTypes, bot: Text, sender_id: Text, **kwargs):
        """
        Adds custom metrics for an end user.

        :param log_type: one of supported MetricTypes.
        :param bot: bot id
        :param sender_id: end user identifier
        :param kwargs: custom metrics that should be added.
        """
        metric = EndUserMetrics(
            log_type=log_type,
            bot=bot,
            sender_id=sender_id,
        )
        for key, value in kwargs.items():
            setattr(metric, key, value)
        metric.save()

    @staticmethod
    def get_logs(bot: Text, start_idx: int = 0, page_size: int = 10, **kwargs):
        """
        Retrieves custom metrics for a particular bot in a paginated fashion.

        :param bot: bot id
        :param start_idx: start index of the page.
        :param page_size: size of the page.
        :return: all the metrics as json.
        """
        metrics = EndUserMetrics.objects(
            bot=bot, **kwargs
        ).order_by("-timestamp").skip(start_idx).limit(page_size).exclude('id').to_json()
        return json.loads(metrics)
