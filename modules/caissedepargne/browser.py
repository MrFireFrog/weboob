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

import re
import datetime
import json

from decimal import Decimal

from weboob.browser import LoginBrowser, need_login, StatesMixin
from weboob.browser.switch import SiteSwitch
from weboob.browser.url import URL
from weboob.capabilities.bank import Account, AddRecipientStep, Recipient, TransferBankError, Transaction
from weboob.capabilities.base import NotAvailable
from weboob.capabilities.profile import Profile
from weboob.browser.exceptions import BrowserHTTPNotFound, ClientError
from weboob.exceptions import BrowserIncorrectPassword, BrowserUnavailable
from weboob.tools.capabilities.bank.transactions import sorted_transactions, FrenchTransaction
from weboob.tools.compat import urljoin
from weboob.tools.value import Value
from weboob.tools.decorators import retry

from .pages import (
    IndexPage, ErrorPage, MarketPage, LifeInsurance, GarbagePage,
    MessagePage, LoginPage,
    TransferPage, ProTransferPage, TransferConfirmPage, TransferSummaryPage,
    SmsPage, SmsPageOption, SmsRequest, AuthentPage, RecipientPage, CanceledAuth, CaissedepargneKeyboard,
    TransactionsDetailsPage, LoadingPage, ConsLoanPage, MeasurePage
)


__all__ = ['CaisseEpargne']


class CaisseEpargne(LoginBrowser, StatesMixin):
    BASEURL = "https://www.caisse-epargne.fr"
    STATE_DURATION = 5

    login = URL('/authentification/manage\?step=identification&identifiant=(?P<login>.*)',
                'https://.*/login.aspx', LoginPage)
    account_login = URL('/authentification/manage\?step=account&identifiant=(?P<login>.*)&account=(?P<accountType>.*)', LoginPage)
    loading = URL('https://.*/CreditConso/ReroutageCreditConso.aspx', LoadingPage)
    cons_loan = URL('https://www.credit-conso-cr.caisse-epargne.fr/websavcr-web/rest/contrat/getContrat\?datePourIe(?P<datepourie>)', ConsLoanPage)
    transaction_detail = URL('https://.*/Portail.aspx.*', TransactionsDetailsPage)
    recipient = URL('https://.*/Portail.aspx.*', RecipientPage)
    transfer = URL('https://.*/Portail.aspx.*', TransferPage)
    transfer_summary = URL('https://.*/Portail.aspx.*', TransferSummaryPage)
    transfer_confirm = URL('https://.*/Portail.aspx.*', TransferConfirmPage)
    pro_transfer = URL('https://.*/Portail.aspx.*', ProTransferPage)
    measure_page = URL('https://.*/Portail.aspx.*', MeasurePage)
    authent = URL('https://.*/Portail.aspx.*', AuthentPage)
    home = URL('https://.*/Portail.aspx.*', IndexPage)
    home_tache = URL('https://.*/Portail.aspx\?tache=(?P<tache>).*', IndexPage)
    error = URL('https://.*/login.aspx',
                'https://.*/Pages/logout.aspx.*',
                'https://.*/particuliers/Page_erreur_technique.aspx.*', ErrorPage)
    market = URL('https://.*/Pages/Bourse.*',
                 'https://www.caisse-epargne.offrebourse.com/ReroutageSJR',
                 'https://www.caisse-epargne.offrebourse.com/Portefeuille.*', MarketPage)
    life_insurance = URL('https://.*/Assurance/Pages/Assurance.aspx',
                         'https://www.extranet2.caisse-epargne.fr.*', LifeInsurance)
    message = URL('https://www.caisse-epargne.offrebourse.com/DetailMessage\?refresh=O', MessagePage)
    garbage = URL('https://www.caisse-epargne.offrebourse.com/Portefeuille',
                  'https://www.caisse-epargne.fr/particuliers/.*/emprunter.aspx',
                  'https://.*/particuliers/emprunter.*',
                  'https://.*/particuliers/epargner.*', GarbagePage)
    sms = URL('https://www.icgauth.caisse-epargne.fr/dacswebssoissuer/AuthnRequestServlet', SmsPage)
    sms_option = URL('https://www.icgauth.caisse-epargne.fr/dacstemplate-SOL/index.html\?transactionID=.*', SmsPageOption)
    request_sms = URL('https://www.icgauth.caisse-epargne.fr/dacsrest/api/v1u0/transaction/(?P<param>)', SmsRequest)
    __states__ = ('BASEURL', 'multi_type', 'typeAccount', 'is_cenet_website', 'recipient_form')

    def __init__(self, nuser, *args, **kwargs):
        self.BASEURL = kwargs.pop('domain', self.BASEURL)
        if not self.BASEURL.startswith('https://'):
            self.BASEURL = 'https://%s' % self.BASEURL

        self.is_cenet_website = False
        self.multi_type = False
        self.accounts = None
        self.loans = None
        self.typeAccount = 'WE'
        self.nuser = nuser
        self.recipient_form = None

        super(CaisseEpargne, self).__init__(*args, **kwargs)

    def load_state(self, state):
        if 'recipient_form' in state and state['recipient_form'] is not None:
            super(CaisseEpargne, self).load_state(state)
            self.logged = True

    def do_login(self):
        """
        Attempt to log in.
        Note: this method does nothing if we are already logged in.
        """
        if not self.username or not self.password:
            raise BrowserIncorrectPassword()

        # Reset domain to log on pro website if first login attempt failed on personal website.
        if self.multi_type:
            self.BASEURL = 'https://www.caisse-epargne.fr'
            self.typeAccount = 'WP'

        data = self.login.go(login=self.username).get_response()

        if data is None:
            raise BrowserIncorrectPassword()

        if "authMode" in data and data['authMode'] == 'redirect':
            raise SiteSwitch('cenet')

        if len(data['account']) > 1:
            self.multi_type = True
            data = self.account_login.go(login=self.username, accountType=self.typeAccount).get_response()

        assert data is not None

        typeAccount = data['account'][0]

        idTokenClavier = data['keyboard']['Id']
        vk = CaissedepargneKeyboard(data['keyboard']['ImageClavier'], data['keyboard']['Num']['string'])
        newCodeConf = vk.get_string_code(self.password)

        playload = {
            'idTokenClavier': idTokenClavier,
            'newCodeConf': newCodeConf,
            'auth_mode': 'ajax',
            'nuusager': self.nuser.encode('utf-8'),
            'codconf': self.password,
            'typeAccount': typeAccount,
            'step': 'authentification',
            'ctx': 'typsrv=WE',
            'clavierSecurise': '1',
            'nuabbd': self.username
        }

        try:
            res = self.location(data['url'], params=playload)
        except ValueError:
            raise BrowserUnavailable()
        if not res.page:
            raise BrowserUnavailable()

        response = res.page.get_response()

        assert response is not None

        if not response['action']:
            if not self.typeAccount == 'WP' and self.multi_type:
                # If we haven't test PRO espace we check before raising wrong pass
                self.do_login()
                return
            raise BrowserIncorrectPassword(response['error'])

        self.BASEURL = urljoin(data['url'], '/')

        try:
            self.home.go()
        except BrowserHTTPNotFound:
            raise BrowserIncorrectPassword()

    def loans_conso(self):
        days = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
        month = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul' , 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
        now = datetime.datetime.today()
        d = '%s %s %s %s:%s:%s GMT 0100 (CET)' % (days[now.weekday()], month[now.month - 1], now.year, now.hour, format(now.minute, "02"), now.second)
        if self.home.is_here() and self.page.loan_unavailable():
            msg = self.page.loan_unavailable_msg()
            if msg:
                self.logger.warning('%s' % msg)
                return None
        self.cons_loan.go(datepourie = d)
        return self.page.get_conso()

    # On home page there is a list of "measure" links, each one leading to one person accounts list.
    # Iter over each 'measure' and navigate to it to get all accounts
    @need_login
    def get_measure_accounts_list(self):
        self.home.go()

        # Make sure we are on list of measures page
        if self.measure_page.is_here():
            self.page.check_no_accounts()
            measure_ids = self.page.get_measure_ids()
            self.accounts = []
            for measure_id in measure_ids:
                self.page.go_measure_accounts_list(measure_id)
                if self.page.check_measure_accounts():
                    for account in list(self.page.get_list()):
                        account._info['measure_id'] = measure_id
                        self.accounts.append(account)
                self.page.go_measure_list()

            for account in self.accounts:
                if 'acc_type' in account._info and account._info['acc_type'] == Account.TYPE_LIFE_INSURANCE:
                    self.page.go_measure_list()
                    self.page.go_measure_accounts_list(account._info['measure_id'])
                    self.page.go_history(account._info)

                    if self.message.is_here():
                        self.page.submit()
                        self.page.go_history(account._info)

                    balance = self.page.get_measure_balance(account)
                    account.balance = Decimal(FrenchTransaction.clean_amount(balance))
                    account.currency = account.get_currency(balance)

        return self.accounts

    @need_login
    def get_accounts_list(self):
        if self.accounts is None:
            self.accounts = self.get_measure_accounts_list()
        if self.accounts is None:
            if self.home.is_here():
                self.page.check_no_accounts()
                self.page.go_list()
            else:
                self.home.go()

            self.accounts = list(self.page.get_list())
            for account in self.accounts:
                if account.type in (Account.TYPE_MARKET, Account.TYPE_PEA):
                    self.home_tache.go(tache='CPTSYNT0')
                    self.page.go_history(account._info)

                    if self.message.is_here():
                        self.page.submit()
                        self.page.go_history(account._info)

                    # Some users may not have access to this.
                    if not self.market.is_here():
                        continue

                    self.page.submit()

                    if self.page.is_error():
                        continue

                    self.garbage.go()

                    if self.garbage.is_here():
                        continue
                    self.page.get_valuation_diff(account)
        return iter(self.accounts)

    @need_login
    def get_loans_list(self):
        if self.loans is None:
            self.loans = []

            if self.home.is_here():
                if self.page.check_no_accounts() or self.page.check_no_loans():
                    return iter([])

            self.home_tache.go(tache='CRESYNT0')

            if self.home.is_here():
                if not self.page.is_access_error():
                    self.page.go_loan_list()
                    self.loans = list(self.page.get_loan_list())

            for _ in range(3):
                try:
                    self.home_tache.go(tache='CPTSYNT0')

                    if self.home.is_here():
                        self.page.go_list()
                except ClientError:
                    pass
                else:
                    break

        return iter(self.loans)

    @need_login
    def _get_history(self, info):
        if isinstance(info['link'], list):
            info['link'] = info['link'][0]
        if not info['link'].startswith('HISTORIQUE'):
            return
        if 'measure_id' in info:
            self.page.go_measure_list()
            self.page.go_measure_accounts_list(info['measure_id'])
        elif self.home.is_here():
            self.page.go_list()
        else:
            self.home_tache.go(tache='CPTSYNT0')

        self.page.go_history(info)

        info['link'] = [info['link']]

        for i in range(100):

            assert self.home.is_here()

            # list of transactions on account page
            transactions_list = []
            list_form = []
            for tr in self.page.get_history():
                transactions_list.append(tr)
                if re.match('^CB [\d]{4}\*{6}[\d]{6} TOT DIF ([\w]{3,9})', tr.label, flags=re.IGNORECASE):
                    list_form.append(self.page.get_form_to_detail(tr))

            # add detail card to list of transactions
            for form in list_form:
                form.submit()
                assert self.transaction_detail.is_here()
                for tr in self.page.get_detail():
                    tr.type = Transaction.TYPE_DEFERRED_CARD
                    transactions_list.append(tr)
                if self.new_website:
                    self.page.go_newsite_back_to_summary()
                else:
                    self.page.go_form_to_summary()

                # going back to summary goes back to first page
                for j in range(i):
                    assert self.page.go_next()

            #  order by date the transactions without the summaries
            transactions_list = sorted_transactions(transactions_list)

            for tr in transactions_list:
                yield tr

            assert self.home.is_here()

            if not self.page.go_next():
                return

        assert False, 'More than 100 history pages'

    @need_login
    def _get_history_invests(self, account):
        if self.home.is_here():
            self.page.go_list()
        else:
            self.home.go()

        self.page.go_history(account._info)

        try:
            self.page.go_life_insurance(account)

            if self.market.is_here() is False and self.message.is_here() is False:
                return iter([])

            self.page.submit()
            self.location('https://www.extranet2.caisse-epargne.fr%s' % self.page.get_cons_histo())

        except (IndexError, AttributeError) as e:
            self.logger.error(e)
            return iter([])
        return self.page.iter_history()

    @need_login
    def get_history(self, account):
        if not hasattr(account, '_info'):
            raise NotImplementedError
        if account.type is Account.TYPE_LIFE_INSURANCE and 'measure_id' not in account._info:
            return self._get_history_invests(account)
        return self._get_history(account._info)

    @need_login
    def get_coming(self, account):
        trs = []

        if not hasattr(account, '_info'):
            raise NotImplementedError()
        for info in account._card_links:
            for tr in self._get_history(info.copy()):
                tr.type = tr.TYPE_DEFERRED_CARD
                tr.nopurge = True
                trs.append(tr)

        return sorted_transactions(trs)

    @need_login
    def get_investment(self, account):
        if account.type not in (Account.TYPE_LIFE_INSURANCE, Account.TYPE_MARKET, Account.TYPE_PEA) or 'measure_id' in account._info:
            raise NotImplementedError()
        if self.home.is_here():
            self.page.go_list()
        else:
            self.home.go()

        self.page.go_history(account._info)
        if account.type in (Account.TYPE_MARKET, Account.TYPE_PEA):
            # Some users may not have access to this.
            if not self.market.is_here():
                return
            self.page.submit()
            if self.page.is_error():
                return
            self.location('https://www.caisse-epargne.offrebourse.com/Portefeuille')
            if self.message.is_here():
                return
                # TODO reraise ActionNeeded when catch by the backend at this stage
                # raise ActionNeeded(self.page.get_message())

            if not self.page.is_on_right_portfolio(account):
                self.location('https://www.caisse-epargne.offrebourse.com/Portefeuille?compte=%s' % self.page.get_compte(account))
        elif account.type is Account.TYPE_LIFE_INSURANCE:
            try:
                self.page.go_life_insurance(account)

                if self.market.is_here() is False and self.message.is_here() is False:
                    return

                self.page.submit()
                self.location('https://www.extranet2.caisse-epargne.fr%s' % self.page.get_cons_repart())
            except (IndexError, AttributeError) as e:
                self.logger.error(e)
                return
        if self.garbage.is_here():
            self.page.come_back()
            return
        for i in self.page.iter_investment():
            yield i
        if self.market.is_here():
            self.page.come_back()

    @need_login
    def get_advisor(self):
        raise NotImplementedError()

    @need_login
    def get_profile(self):
        from weboob.tools.misc import to_unicode
        profile = Profile()
        if len([k for k in self.session.cookies.keys() if k == 'CTX']) > 1:
            del self.session.cookies['CTX']
        elif 'username=' in self.session.cookies.get('CTX', ''):
            profile.name = to_unicode(re.search('username=([^&]+)', self.session.cookies['CTX']).group(1))
        elif 'nomusager=' in self.session.cookies.get('headerdei'):
            profile.name = to_unicode(re.search('nomusager=(?:[^&]+/ )?([^&]+)', self.session.cookies['headerdei']).group(1))
        return profile

    @need_login
    def iter_recipients(self, origin_account):
        if origin_account.type == Account.TYPE_LOAN:
            return []

        # Transfer unavailable
        try:
            self.pre_transfer(origin_account)
        except TransferBankError:
            return []
        if self.page.transfer_unavailable() or self.page.need_auth() or not self.page.can_transfer(origin_account):
            return []
        return self.page.iter_recipients(account_id=origin_account.id)

    def pre_transfer(self, account):
        if self.home.is_here():
            if 'measure_id' in account._info:
                self.page.go_measure_list()
                self.page.go_measure_accounts_list(account._info['measure_id'])
            else:
                self.page.go_list()
        else:
            self.home.go()
        self.page.go_transfer(account)
        if self.pro_transfer.is_here():
            raise NotImplementedError()

    @need_login
    def init_transfer(self, account, recipient, transfer):
        self.pre_transfer(account)
        self.page.init_transfer(account, recipient, transfer)
        self.page.continue_transfer(account.label, recipient, transfer.label)
        return self.page.create_transfer(account, recipient, transfer)

    @need_login
    def execute_transfer(self, transfer):
        self.page.confirm()
        return self.page.populate_reference(transfer)

    def get_recipient_obj(self, recipient):
        r = Recipient()
        r.iban = recipient.iban
        r.id = recipient.iban
        r.label = recipient.label
        r.category = u'Externe'
        r.enabled_at = datetime.datetime.now().replace(microsecond=0)
        r.currency = u'EUR'
        r.bank_name = NotAvailable
        return r

    def post_sms_password(self, sms_password):
        data = {}
        for k, v in self.recipient_form.items():
            if k != 'url':
                data[k] = v
        data['uiAuthCallback__1_'] = sms_password
        self.location(self.recipient_form['url'], data=data)

    def facto_post_recip(self, recipient):
        self.page.post_recipient(recipient)
        self.page.confirm_recipient()
        return self.get_recipient_obj(recipient)

    def end_sms_recipient(self, recipient, **params):
        self.post_sms_password(params['sms_password'])
        self.recipient_form = None
        self.page.post_form()
        self.page.go_on()
        self.facto_post_recip(recipient)

    @retry(CanceledAuth)
    @need_login
    def new_recipient(self, recipient, **params):
        if 'sms_password' in params:
            return self.end_sms_recipient(recipient, **params)

        if 'otp_sms' in params:
            transactionid = re.search(r'transactionID=(.*)', self.page.url).group(1)
            self.request_sms.go(param = transactionid)
            validation = {}
            validation['validate'] = {}
            key = self.page.validate_key()
            validation['validate'][key] = []
            inner_param = {}
            inner_param['id'] = self.page.validation_id(key)
            inner_param['type'] = 'SMS'
            inner_param['otp_sms'] = params['otp_sms']
            validation['validate'][key].append(inner_param)
            headers = {'Content-Type': 'application/json', 'Accept':'application/json, text/plain, */*'}
            self.location(self.url +'/step' , data=json.dumps(validation), headers=headers)
            saml = self.page.get_saml()
            action = self.page.get_action()
            self.location(action, data={'SAMLResponse':saml})
            if self.authent.is_here():
                self.page.go_on()
                return self.facto_post_recip(recipient)

        self.pre_transfer(next(acc for acc in self.get_accounts_list() if acc.type in (Account.TYPE_CHECKING, Account.TYPE_SAVINGS)))
        # This send sms to user.
        self.page.go_add_recipient()
        if self.sms_option.is_here() :
            raise AddRecipientStep(self.get_recipient_obj(recipient), Value('otp_sms',
            label=u'Veuillez renseigner le mot de passe unique qui vous a été envoyé par SMS dans le champ réponse.'))

        else:
            self.page.check_canceled_auth()
            self.page.set_browser_form()
            raise AddRecipientStep(self.get_recipient_obj(recipient), Value('sms_password', label=self.page.get_prompt_text()))
