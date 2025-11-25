from kairon.exceptions import AppException
from kairon.pos.odoo.odoo_pos import OdooPOS
from kairon.shared.pos.constants import POSType


class POSFactory:

    pos_types = {
        POSType.odoo.value: OdooPOS
    }

    @staticmethod
    def get_instance(pos_type: POSType):

        if pos_type not in POSFactory.pos_types.keys():
            raise AppException(f"{pos_type} is not valid")
        return POSFactory.pos_types[pos_type]