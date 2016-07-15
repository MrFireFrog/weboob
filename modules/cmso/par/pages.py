# -*- coding: utf-8 -*-

# Copyright(C) 2016      Edouard Lambert
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
from datetime import datetime as dt

from weboob.browser.pages import HTMLPage, JsonPage, RawPage, LoggedPage, pagination
from weboob.browser.elements import DictElement, ItemElement, TableElement, method
from weboob.browser.filters.standard import CleanText, Upper, Date, Regexp, CleanDecimal, Env, TableCell, Field
from weboob.browser.filters.json import Dict
from weboob.browser.filters.html import Attr, Link
from weboob.capabilities.bank import Account, Investment
from weboob.capabilities.base import NotAvailable
from weboob.tools.capabilities.bank.transactions import FrenchTransaction
from weboob.exceptions import BrowserUnavailable


def MyDecimal(*args, **kwargs):
    kwargs.update(replace_dots=True, default=NotAvailable)
    return CleanDecimal(*args, **kwargs)


class LogoutPage(RawPage):
    pass


class InfosPage(LoggedPage, HTMLPage):
    def get_typelist(self):
        url = Attr(None, 'src').filter(self.doc.xpath('//script[contains(@src, "comptes/scripts")]'))
        m = re.search('synthesecomptes[^\w]+([^:]+)[^\w]+([^"]+)', self.browser.open(url).content)
        return {m.group(1): m.group(2)}


class AccountsPage(LoggedPage, JsonPage):
    TYPES = {'courant': Account.TYPE_CHECKING, 'preference': Account.TYPE_LOAN, 'vie': \
            Account.TYPE_LIFE_INSURANCE, 'actions': Account.TYPE_MARKET, 'titres': \
            Account.TYPE_MARKET, 'livret': Account.TYPE_SAVINGS, 'epargne logement': \
            Account.TYPE_SAVINGS}

    def get_keys(self):
        return [k for k, v in self.doc.items() if v and isinstance(v, (dict, list)) and "exception" not in self.doc]

    def check_response(self):
        if "exception" in self.doc:
            raise BrowserUnavailable("Please use the right website.")

    @method
    class iter_accounts(DictElement):
        def parse(self, el):
            self.item_xpath = "%s/*" % Env('key')(self)

        def find_elements(self):
            selector = self.item_xpath.split('/')
            for el in selector:
                if isinstance(self.el, dict) and el == '*' and self.el.values():
                    self.el = self.el.values()[0]
                if el == '*':
                    continue
                self.el = self.el[el]
            for el in self.el:
                yield el

        class item(ItemElement):
            klass = Account

            obj_id = Dict('index')
            obj_label = Upper(Dict('lib'))
            obj_balance = CleanDecimal(Dict('soldeEuro', default="0"))
            obj_number = Dict('identifiantTechnique')
            obj_currency =  Dict('deviseCompteCode')
            obj_coming = CleanDecimal(Dict('AVenir', default=None), default=NotAvailable)

            def obj_type(self):
                return self.page.TYPES.get(Dict('accountType', default=None)(self).lower(), Account.TYPE_UNKNOWN)

            def condition(self):
                return "LIVRET" not in Dict('accountType')(self)

    @method
    class iter_products(DictElement):
        def parse(self, el):
            self.item_xpath = "%s/*/savingsProducts/*/savingsAccounts" % Env('key')(self)

        class item(ItemElement):
            klass = Account

            obj_id = Dict('index')
            obj_label = Upper(Dict('libelleContrat'))
            obj_balance = CleanDecimal(Dict('solde', default="0"))
            obj_number = Dict('technicalIndex')
            obj_coming = CleanDecimal(Dict('AVenir', default=None), default=NotAvailable)

            def obj_type(self):
                for key in self.page.TYPES:
                    if key in Dict('libelleContrat')(self).lower():
                        return self.page.TYPES[key]
                return Account.TYPE_UNKNOWN


class Transaction(FrenchTransaction):
    PATTERNS = [(re.compile(u'^(?P<text>CARTE.*)'),  FrenchTransaction.TYPE_CARD),
                (re.compile(u'^(?P<text>(PRLV|PRELEVEMENTS).*)'), FrenchTransaction.TYPE_ORDER),
                (re.compile(u'^(?P<text>RET DAB.*)'), FrenchTransaction.TYPE_WITHDRAWAL),
                (re.compile(u'^(?P<text>ECH.*)'), FrenchTransaction.TYPE_LOAN_PAYMENT),
                (re.compile(u'^(?P<text>VIR.*)'), FrenchTransaction.TYPE_TRANSFER),
                (re.compile(u'^(?P<text>ANN.*)'), FrenchTransaction.TYPE_PAYBACK),
                (re.compile(u'^(?P<text>(VRST|VERSEMENT).*)'), FrenchTransaction.TYPE_DEPOSIT),
                (re.compile(u'^(?P<text>.*)'), FrenchTransaction.TYPE_BANK),
               ]


class HistoryPage(LoggedPage, JsonPage):
    def get_keys(self):
        return [k for k, v in self.doc.items() if v and isinstance(v, (dict, list))]

    @method
    class iter_history(DictElement):
        def parse(self, el):
            # Key only if coming
            key = Env('key', default=None)(self)
            self.item_xpath = "%s/operationList" % key if key and "CardList" not in key \
                              else "%s/currentMonthCardList/*/listeOperations/*" % key \
                              if key else "listOperationProxy"

        class item(ItemElement):
            klass = Transaction

            obj_raw = Transaction.Raw(Dict('libelleCourt'))
            obj_vdate = Date(Dict('dateValeur'), dayfirst=True)
            obj_amount = CleanDecimal(Dict('montantEnEuro'), default=NotAvailable)

            def obj_date(self):
                return dt.fromtimestamp(int(Dict('dateOperation')(self)[:-3]))


class LifeinsurancePage(LoggedPage, HTMLPage):
    def get_link(self, page):
        return Link().filter(self.doc.xpath(u'//a[contains(text(), "%s")]' % page))

    @pagination
    @method
    class iter_history(TableElement):
        item_xpath = '//table/tbody/tr[contains(@class, "results")]'
        head_xpath = '//table/thead/tr/th'

        col_date = re.compile('Date')
        col_label = re.compile(u'Libellé')
        col_amount = re.compile('Montant')

        next_page = Link('//a[contains(text(), "Suivant") and not(contains(@href, "javascript"))]', default=None)

        class item(ItemElement):
            klass = Transaction

            obj_raw = Transaction.Raw(TableCell('label'))
            obj_date = Date(CleanText(TableCell('date')), dayfirst=True)
            obj_amount = MyDecimal(TableCell('amount'))

    @method
    class iter_investment(TableElement):
        item_xpath = '//table/tbody/tr[contains(@class, "results")]'
        head_xpath = '//table/thead/tr/th'

        col_label = re.compile(u'Libellé')
        col_quantity = re.compile('Nb parts')
        col_vdate = re.compile('Date VL')
        col_unitvalue = re.compile('VL')
        col_unitprice = re.compile('Prix de revient')
        col_valuation = re.compile('Solde')

        class item(ItemElement):
            klass = Investment

            obj_label = CleanText(TableCell('label'))
            obj_code = Regexp(Link('./td/a'), 'Isin%253D([^%]+)')
            obj_quantity = MyDecimal(TableCell('quantity'))
            obj_unitprice = MyDecimal(TableCell('unitprice'))
            obj_unitvalue = MyDecimal(TableCell('unitvalue'))
            obj_valuation = MyDecimal(TableCell('valuation'))
            obj_vdate = Date(CleanText(TableCell('vdate')), dayfirst=True, default=NotAvailable)


class MarketPage(LoggedPage, HTMLPage):
    def get_list(self, acclabel):
        for a in self.doc.xpath('//a[contains(@onclick, "indiceCompte")]'):
            if CleanText().filter(a.xpath('.')) == acclabel:
                ids = re.search('indiceCompte[^\d]+(\d+).*idRacine[^\d]+(\d+)', \
                      Attr(None, 'onclick').filter(a.xpath('.'))).groups()
                break
        form = self.get_form(name="formCompte")
        form ['indiceCompte'] = ids[0]
        form ['idRacine'] = ids[1]
        return form.submit()

    def get_full_list(self):
        form = self.get_form(name="formOperation")
        form['dateDebut'] = "02/01/1970"
        return form.submit()

    @method
    class iter_history(TableElement):
        item_xpath = '//table[has-class("domifrontTb")]/tr[not(has-class("LnTit") or has-class("LnTot"))]'
        head_xpath = '//table[has-class("domifrontTb")]/tr[1]/td'

        col_date = re.compile('Date')
        col_label = u'Opération'
        col_code = u'Code'
        col_quantity = u'Quantité'
        col_amount = re.compile('Montant')

        class item(ItemElement):
            klass = Transaction

            obj_label = CleanText(TableCell('label'))
            obj_type = Transaction.TYPE_BANK
            obj_date = Date(CleanText(TableCell('date')), dayfirst=True)
            obj_amount = CleanDecimal(TableCell('amount'))
            obj_investments = Env('investments')

            def parse(self, el):
                i = Investment()
                i.label = Field('label')(self)
                i.code = CleanText(TableCell('code'))(self)
                i.quantity = MyDecimal(TableCell('quantity'))(self)
                i.valuation = Field('amount')(self)
                i.vdate = Field('date')(self)
                self.env['investments'] = [i]

    @method
    class iter_investment(TableElement):
        item_xpath = '//table/tr[not(has-class("LnTit") or has-class("LnTot"))]'
        head_xpath = '//table/tr[1]/td'

        col_label = u'Valeur'
        col_code = u'Code'
        col_quantity = u'Qté'
        col_vdate = u'Date cours'
        col_unitvalue = u'Cours'
        col_unitprice = re.compile('P.R.U')
        col_valuation = u'Valorisation'

        class item(ItemElement):
            klass = Investment

            obj_label = Upper(TableCell('label'))
            obj_code = CleanText(TableCell('code'))
            obj_quantity = CleanDecimal(TableCell('quantity'), default=NotAvailable)
            obj_unitprice = MyDecimal(TableCell('unitprice'))
            obj_unitvalue = MyDecimal(TableCell('unitvalue'))
            obj_valuation = CleanDecimal(TableCell('valuation'))
            obj_vdate = Date(CleanText(TableCell('vdate')), dayfirst=True, default=NotAvailable)

            def condition(self):
                return not CleanText('//div[has-class("errorConteneur")]', default=None)(self)
