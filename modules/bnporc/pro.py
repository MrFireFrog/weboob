# -*- coding: utf-8 -*-

# Copyright(C) 2009-2013  Romain Bignon
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.


import re
from urlparse import urlparse, parse_qsl
from decimal import Decimal

from weboob.capabilities.bank import Account
from weboob.tools.browser import BasePage

from .perso.transactions import Transaction


__all__ = ['ProAccountsList', 'ProAccountHistory']


class ProAccountsList(BasePage):
    COL_LABEL   = 1
    COL_ID      = 2
    COL_BALANCE = 3
    COL_COMING  = 5

    def get_list(self):
        for tr in self.document.xpath('//tr[@class="comptes"]'):
            cols = tr.findall('td')

            account = Account()
            account.id = self.parser.tocleanstring(cols[self.COL_ID])
            account.label = self.parser.tocleanstring(cols[self.COL_LABEL])
            account.balance = Decimal(self.parser.tocleanstring(cols[self.COL_BALANCE]))
            account.coming = Decimal(self.parser.tocleanstring(cols[self.COL_COMING]))
            account._link_id = None
            account._stp = None

            a = cols[self.COL_LABEL].find('a')
            if a is not None:
                url = urlparse(a.attrib['href'])
                p = dict(parse_qsl(url.query))
                account._link_id = p.get('ch4', None)
                account._stp = p.get('stp', None)

            yield account


class ProAccountHistory(BasePage):
    COL_DATE = 0
    COL_LABEL = 1
    COL_DEBIT = -2
    COL_CREDIT = -1

    def iter_operations(self):
        for i, tr in enumerate(self.document.xpath('//tr[@class="hdoc1" or @class="hdotc1"]')):
            if 'bgcolor' not in tr.attrib:
                continue
            cols = tr.findall('td')

            op = Transaction(i)

            date = self.parser.tocleanstring(cols[self.COL_DATE])
            raw = self.parser.tocleanstring(cols[self.COL_LABEL])
            raw = re.sub(r'[ \xa0]+', ' ', raw).strip()
            op.parse(date=date, raw=raw)

            debit = self.parser.tocleanstring(cols[self.COL_DEBIT])
            credit = self.parser.tocleanstring(cols[self.COL_CREDIT])
            op.set_amount(credit, debit)

            yield op

    def iter_coming_operations(self):
        raise NotImplementedError()
