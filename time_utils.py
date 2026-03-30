from datetime import datetime
from zoneinfo import ZoneInfo
import os


APP_TIMEZONE = os.getenv('APP_TIMEZONE', 'America/Sao_Paulo')
SAO_PAULO_TZ = ZoneInfo(APP_TIMEZONE)
DB_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
PROTHEUS_DATE_FORMAT = '%Y%m%d'


def agora_sp():
    return datetime.now(SAO_PAULO_TZ)


def agora_sp_str():
    return agora_sp().strftime(DB_DATETIME_FORMAT)


def parse_db_datetime(valor):
    return datetime.strptime(valor, DB_DATETIME_FORMAT).replace(tzinfo=SAO_PAULO_TZ)


def parse_protheus_date(valor):
    return datetime.strptime(str(valor), PROTHEUS_DATE_FORMAT).date()


def format_protheus_date(valor):
    return valor.strftime(PROTHEUS_DATE_FORMAT)
