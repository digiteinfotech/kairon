import calendar
from datetime import datetime, date
from typing import Text

from mongoengine import DoesNotExist
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.data_object import Metering


class MeteringProcessor:
    """

    """

    @staticmethod
    def add_metrics(bot: Text, account: int, metric_type: MetricType):
        """
        Adds custom metrics for an end user.

        :param bot: bot id
        :param account: account id
        :param metric_type: metric_type
        """
        try:
            first_day_of_month = datetime.utcnow().date()
            metric = Metering.objects(bot=bot, metric_type=metric_type.value, account=account, date=first_day_of_month).get()
            metric.data = metric.data + 1
        except DoesNotExist:
            metric = Metering(bot=bot, metric_type=metric_type.value, account=account, data=1)
        metric.save()

    @staticmethod
    def get_metrics(account: int, metric_type: str, start_date: date = None, end_date: date = None):
        """
        Retrieves custom metrics for a particular bot in a paginated fashion.

        :param account: account
        :param metric_type: metric_type
        :param start_date: start date
        :param end_date: end date
        :return: all the metrics as json.
        """
        if not start_date:
            start_date = datetime.utcnow().date().replace(day=1)
        if not end_date:
            month = datetime.utcnow().date().month
            year = datetime.utcnow().date().year
            end_date = datetime.utcnow().date().replace(day=calendar.monthrange(year, month)[1])
        metric_count = list(Metering.objects(
            account=account, metric_type=metric_type.value, date__gte=start_date, date__lte=end_date
        ).aggregate([{"$group": {"_id": "$bot", "count": {"$sum": "$data"}}}]))
        return metric_count
