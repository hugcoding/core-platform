"""Inclusive booking-date bounds, without loading financial data."""
import calendar
from datetime import date
import re


def period_bounds(month='', year='', date_from='', date_to=''):
    if sum((bool(month), bool(year), bool(date_from or date_to))) > 1:
        raise ValueError('conflicting_period')
    if month:
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}', month):
            raise ValueError('invalid_period')
        start = date.fromisoformat(month+'-01')
        return start, date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
    if year:
        if not re.fullmatch(r'[0-9]{4}', year):
            raise ValueError('invalid_period')
        return date(int(year), 1, 1), date(int(year), 12, 31)
    if date_from or date_to:
        if not all(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', v) for v in (date_from, date_to)):
            raise ValueError('invalid_period')
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
        if start > end:
            raise ValueError('invalid_period')
        return start, end
    return None
