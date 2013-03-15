# -*- coding: utf-8 -*-

# Copyright(C) 2012 Romain Bignon
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


from decimal import Decimal
import re
from cStringIO import StringIO

from weboob.tools.browser import BasePage, BrokenPageError
from weboob.tools.json import json
from weboob.capabilities.bank import Account
from weboob.tools.capabilities.bank.transactions import FrenchTransaction


__all__ = ['LoginPage', 'AccountsPage', 'TransactionsPage']


class LoginPage(BasePage):
    pass


class CDNBasePage(BasePage):
    def get_from_js(self, pattern, end, is_list=False):
        """
        find a pattern in any javascript text
        """
        value = None
        for script in self.document.xpath('//script'):
            txt = script.text
            if txt is None:
                continue

            start = txt.find(pattern)
            if start < 0:
                continue

            while 1:
                if value is None:
                    value = ''
                else:
                    value += ','
                value += txt[start+len(pattern):start+txt[start+len(pattern):].find(end)+len(pattern)]

                if not is_list:
                    break

                txt = txt[start+len(pattern)+txt[start+len(pattern):].find(end):]

                start = txt.find(pattern)
                if start < 0:
                    break
            return value

    def get_execution(self):
        return self.get_from_js("name: 'execution', value: '", "'")


class AccountsPage(CDNBasePage):
    COL_HISTORY = 2
    COL_ID = 4
    COL_LABEL = 5
    COL_BALANCE = -1

    def get_history_link(self):
        return self.parser.strip(self.get_from_js(",url: Ext.util.Format.htmlDecode('", "'"))

    def get_list(self):
        accounts = []

        txt = self.get_from_js('_data = new Array(', ');', is_list=True)

        if txt is None:
            raise BrokenPageError('Unable to find accounts list in scripts')

        data = json.loads('[%s]' % txt.replace("'", '"'))

        for line in data:
            a = Account()
            a.id = line[self.COL_ID].replace(' ','')
            fp = StringIO(unicode(line[self.COL_LABEL]).encode(self.browser.ENCODING))
            a.label = self.parser.tocleanstring(self.parser.parse(fp, self.browser.ENCODING).xpath('//div[@class="libelleCompteTDB"]')[0])
            a.balance = Decimal(FrenchTransaction.clean_amount(line[self.COL_BALANCE]))
            a._link = self.get_history_link()
            a._execution = self.get_execution()
            if line[self.COL_HISTORY] == 'true':
                a._link_id = line[self.COL_ID]
            else:
                a._link_id = None

            if a.id.find('_CarteVisa') >= 0:
                accounts[0]._card_ids.append(a._link_id)
                if not accounts[0].coming:
                    accounts[0].coming = Decimal('0.0')
                accounts[0].coming += a.balance
                continue

            a._card_ids = []
            accounts.append(a)

        return iter(accounts)


class Transaction(FrenchTransaction):
    PATTERNS = [(re.compile(r'^(?P<text>RET DAB \w+ .*?) LE (?P<dd>\d{2})(?P<mm>\d{2})$'),
                                                            FrenchTransaction.TYPE_WITHDRAWAL),
                (re.compile(r'^VIR(EMENT)?( INTERNET)?(\.| )?(DE)? (?P<text>.*)'),
                                                            FrenchTransaction.TYPE_TRANSFER),
                (re.compile(r'^PRLV (DE )?(?P<text>.*?)( Motif :.*)?$'),
                                                            FrenchTransaction.TYPE_ORDER),
                (re.compile(r'^CB (?P<text>.*) LE (?P<dd>\d{2})\.?(?P<mm>\d{2})$'),
                                                            FrenchTransaction.TYPE_CARD),
                (re.compile(r'^CHEQUE.*'),                  FrenchTransaction.TYPE_CHECK),
                (re.compile(r'^(CONVENTION \d+ )?COTISATION (?P<text>.*)'),
                                                            FrenchTransaction.TYPE_BANK),
                (re.compile(r'^REM(ISE)?\.?( CHQ\.)? .*'),  FrenchTransaction.TYPE_DEPOSIT),
                (re.compile(r'^(?P<text>.*?)( \d{2}.*)? LE (?P<dd>\d{2})\.?(?P<mm>\d{2})$'),
                                                            FrenchTransaction.TYPE_CARD),
               ]


class TransactionsPage(CDNBasePage):
    COL_ID = 0
    COL_DATE = 1
    COL_DEBIT_DATE = 2
    COL_LABEL = 3
    COL_VALUE = -1

    is_coming = None

    def is_last(self):
        for script in self.document.xpath('//script'):
            txt = script.text
            if txt is None:
                continue

            if txt.find('clicChangerPageSuivant') >= 0:
                return False

        return True

    def get_history(self):
        txt = self.get_from_js('ListeMvts_data = new Array(', ');')

        if txt is None:
            raise BrokenPageError('Unable to find transactions list in scripts')

        data = json.loads('[%s]' % txt.replace('"', '\\"').replace("'", '"'))

        for line in data:
            t = Transaction(line[self.COL_ID])

            if self.is_coming is not None:
                t.type = t.TYPE_CARD
                date = self.parser.strip(line[self.COL_DEBIT_DATE])
            else:
                date = self.parser.strip(line[self.COL_DATE])
            raw = self.parser.strip(line[self.COL_LABEL])

            t.parse(date, raw)
            t.set_amount(line[self.COL_VALUE])

            if self.is_coming is not None and raw.startswith('TOTAL DES') and t.amount > 0:
                # ignore card credit and next transactions are already debited
                self.is_coming = False
                continue
            if self.is_coming is None and raw.startswith('ACHATS CARTE'):
                # Ignore card debit
                continue

            t._is_coming = bool(self.is_coming)
            yield t
