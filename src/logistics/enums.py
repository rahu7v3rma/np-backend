from enum import Enum


class LogisticsCenterEnum(str, Enum):
    ORIAN = 'Orian'
    PICK_AND_PACK = 'Pick and Pack'


class LogisticsCenterMessageTypeEnum(Enum):
    INBOUND_RECEIPT = 'Inbound receipt'
    ORDER_STATUS_CHANGE = 'Order status change'
    SHIP_ORDER = 'Ship order'
    SNAPSHOT = 'Snapshot'
    INBOUND_STATUS_CHANGE = 'Inbound status change'
