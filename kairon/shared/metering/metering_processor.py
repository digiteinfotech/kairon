import calendar
import ujson as json
from datetime import datetime, date
from typing import Text

from starlette.requests import Request

from kairon import Utility
from kairon.shared.constants import PluginTypes
from kairon.shared.metering.constants import MetricType, UpdateMetricType
from kairon.shared.metering.data_object import Metering
from kairon.shared.plugins.factory import PluginFactory


class MeteringProcessor:
    """

    """

    @staticmethod
    def add_metrics(bot: Text, account: int, metric_type: Text, **kwargs):
        """
        Adds custom metrics for an end user.

        :param bot: bot id
        :param account: account id
        :param metric_type: metric_type
        """
        metric = Metering(bot=bot, metric_type=metric_type, account=account)
        for key, value in kwargs.items():
            setattr(metric, key, value)
        metric.save()
        return metric.id.__str__()

    @staticmethod
    def update_metrics(id: Text, bot: Text, metric_type: Text, **kwargs):
        """
        update custom metrics for an end user.

        :param id: id
        :param bot: bot id
        :param account: account id
        :param metric_type: metric_type
        """
        if metric_type not in UpdateMetricType._value2member_map_.keys():
            raise ValueError(f"Invalid metric type {metric_type}")

        metric = Metering.objects(bot=bot, metric_type=metric_type).get(id=id)
        for key, value in kwargs.items():
            setattr(metric, key, value)
        metric.save()

    @staticmethod
    def add_log(metric_type: Text, **kwargs):
        """
        Adds custom metrics for an end user.

        :param metric_type: metric_type
        """
        metric = Metering(metric_type=metric_type)
        for key, value in kwargs.items():
            setattr(metric, key, value)
        metric.save()

    @staticmethod
    def get_metric_count(account: int, metric_type: Text, start_date: date = None, end_date: date = None, **kwargs):
        """
        Retrieves custom metrics for a particular bot in a paginated fashion.

        :param account: account
        :param metric_type: metric_type
        :param start_date: start date
        :param end_date: end date
        :return: all the metrics as json.
        """
        if not start_date:
            start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not end_date:
            month = datetime.utcnow().date().month
            year = datetime.utcnow().date().year
            end_date = datetime.utcnow().replace(day=calendar.monthrange(year, month)[1])
        kwargs.update({"account": account, "metric_type": metric_type, "timestamp__gte": start_date,
                       "timestamp__lte": end_date})
        metric_count = Metering.objects(**kwargs).count()
        return metric_count

    @staticmethod
    def add_log_with_geo_location(metric_type: MetricType, account_id: int, request: Request, bot: Text = None, **kwargs):
        ip = Utility.get_client_ip(request)
        if not Utility.check_empty_string(ip):
            location_info = PluginFactory.get_instance(PluginTypes.ip_info).execute(ip=ip)
            if location_info and ip:
                data = list(location_info.values())
                if data and isinstance(data[0], dict):
                    kwargs.update(data[0])
        return MeteringProcessor.add_metrics(bot, account_id, metric_type, **kwargs)

    @staticmethod
    def get_logs(account: int, start_idx: int = 0, page_size: int = 10, start_date: datetime = None,
                 end_date: datetime = None, **kwargs):
        """
        Retrieves custom metrics for a particular bot in a paginated fashion.

        :param start_date: start date
        :param end_date: end date
        :param account: account id
        :param start_idx: start index of the page.
        :param page_size: size of the page.
        :return: all the metrics as json.
        """
        from kairon.shared.data.processor import MongoProcessor

        if not start_date:
            start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not end_date:
            month = datetime.utcnow().date().month
            year = datetime.utcnow().date().year
            end_date = datetime.utcnow().replace(day=calendar.monthrange(year, month)[1])
        kwargs.update({"account": account, "timestamp__gte": start_date, "timestamp__lte": end_date})
        metrics = Metering.objects(**kwargs).order_by("-timestamp").skip(start_idx).limit(page_size) \
            .exclude('id').to_json()

        row_cnt = MongoProcessor().get_row_count(Metering, **kwargs)
        data = {
            "logs": json.loads(metrics),
            "total": row_cnt
        }
        return data
