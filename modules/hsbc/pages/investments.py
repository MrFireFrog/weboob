# coding: utf-8

from __future__ import unicode_literals
from __future__ import division

import datetime
import json
import time

from weboob.capabilities import NotAvailable
from weboob.capabilities.bank import Account, Investment

from weboob.browser.elements import ItemElement, DictElement, method
from weboob.browser.pages import HTMLPage, JsonPage, LoggedPage
from weboob.browser.filters.standard import (
    CleanText, CleanDecimal, Regexp, Eval, Currency
)
from weboob.browser.filters.json import Dict
from weboob.browser.filters.javascript import JSVar


class LogonInvestmentPage(LoggedPage, HTMLPage):
    """Transient page to the real application page."""
    SESSION_INFO = {}

    def on_load(self):
        _, app_data = self.get_session_storage()
        self.SESSION_INFO['app_location'] = JSVar(var='window.location').filter(self.content.decode())
        self.SESSION_INFO['app_data'] = app_data
        self.browser.SESSION_INFO = self.SESSION_INFO

    def is_here(self):
        return 'appPage.min.html' in self.content.decode('iso-8859-1')

    def get_session_storage(self):
        sessionContent = Regexp(
            CleanText('//script[@type="text/javascript"]'),
            'sessionStorage.setItem\((.*)\)'
        )(self.doc)
        key, value = map(lambda x: x.strip("'").strip(), sessionContent.split(",", 1))
        return key, json.decoder.JSONDecoder().decode(value)


class ProductViewHelper():
    URL = 'https://investissements.clients.hsbc.fr/group-wd-gateway-war/gateway/wd/RetrieveProductView'

    def __init__(self, browser):
        self.browser = browser

    def raw_post_data(self):
        null = None
        return {
            "aggregateXRaySegmentFilter": [],
            "businessOpUnit": "141",
            "cacheRefreshIndicator": null,
            "functionIndicator": [
                {"functionMessageTriggerDescription": "MyPortfolio-MyHoldings|R01"}
            ],
            "holdingAccountInformation": {
                "accountFilterIndicator": "N",
                "accountFilterRefreshIndicator": "Y",
                "cacheRefreshIndicator": "Y",
                "holdingGroupingViewConfig": "ASSETTYPE",
                "investmentHistoryRequestTypeCode": "CURR",
                "priceQuoteTypeCode": "Delay",
                "productDashboardTypeInformation": [
                    {"productDashboardTypeCode": "EQ"},
                    {"productDashboardTypeCode": "BOND"},
                    {"productDashboardTypeCode": "MNYUT"},
                    {"productDashboardTypeCode": "DIVUT"},
                    {"productDashboardTypeCode": "EURO"},
                    {"productDashboardTypeCode": "SI"},
                    {"productDashboardTypeCode": "FCPI"},
                    {"productDashboardTypeCode": "SCPI"},
                    {"productDashboardTypeCode": "ALT"},
                    {"productDashboardTypeCode": "LCYDEP"},
                    {"productDashboardTypeCode": "FCYDEP"},
                    {"productDashboardTypeCode": "INVTINSUR"},
                    {"productDashboardTypeCode": "NONINVTINSUR"},
                    {"productDashboardTypeCode": "LOAN"},
                    {"productDashboardTypeCode": "MORTGAGE"},
                    {"productDashboardTypeCode": "CARD"},
                    {"productDashboardTypeCode": "UWCASH"}
                ],
                "transactionRangeStartDate": null,
                "watchListFilterIndicator": "N"
            },
            "holdingSegmentFilter": [],
            "orderStatusFilter": [
                {"orderStatusGroupIdentifier": "HOLDING", "productCode": null, "productDashboardTypeCode": null},
                {"orderStatusGroupIdentifier": "PENDING", "productCode": null, "productDashboardTypeCode": null}
            ],
            "paginationRequest": [],
            "portfolioAnalysisFilter": [],
            "segmentFilter": [
                {"dataSegmentGroupIdentifier": "PRTFDTLINF"},
                {"dataSegmentGroupIdentifier": "PORTFTLINF"},
                {"dataSegmentGroupIdentifier": "ACCTGRPINF"},
                {"dataSegmentGroupIdentifier": "ACCTFLTINF"}
            ],
            "sortingCriterias": [],
            "staffId": null,
            "watchlistFilter": []
        }

    def investment_list_post_data(self):
        raw_data = self.raw_post_data()
        raw_data.pop('aggregateXRaySegmentFilter')
        raw_data.pop('holdingSegmentFilter')
        raw_data.pop('portfolioAnalysisFilter')
        raw_data.pop('watchlistFilter')
        raw_data.pop('cacheRefreshIndicator')
        raw_data.update({
            "functionIndicator": [
                {"functionMessageTriggerDescription": "MyPortfolio-MyHoldings"}
            ],
            "holdingAccountInformation": {
                "accountFilterIndicator": "N",
                "accountFilterRefreshIndicator": "N",
                "cacheRefreshIndicator": "N",
                "holdingGroupingViewConfig": "ASSETTYPE",
                "investmentHistoryRequestTypeCode": "CURR",
                "priceQuoteTypeCode": "Delay",
                "productDashboardTypeInformation": [
                    {"productDashboardTypeCode": "EQ"}
                ],
                "watchListFilterIndicator": "N"
            },
            "orderStatusFilter": [
                {"orderStatusGroupIdentifier": "HOLDING"},
                {"orderStatusGroupIdentifier": "PENDING"}
            ],
            "segmentFilter": [
                {"dataSegmentGroupIdentifier": "HLDORDRINF"},
                {"dataSegmentGroupIdentifier": "HLDGSUMINF"}
            ],
            "sortingCriterias": [
                {"sortField": "PROD-DSHBD-TYP-CDE", "sortOrder": "+"},
                {"sortField": "PRD-DSHBD-STYP-CDE", "sortOrder": "+"},
                {"sortField": "PROD-SHRT-NAME", "sortOrder": "+"}
            ],
        })
        return raw_data

    def liquidity_account_post_data(self):
        base_data = self.investment_list_post_data()
        base_data.update({
            "segmentFilter": [{"dataSegmentGroupIdentifier": "HLDORDRINF"}],
            "sortingCriterias": [
                {"sortField": "ACCT-NUM", "sortOrder": "+"},
                {"sortField": "ACCT-PROD-TYPE-STR", "sortOrder": "+"},
                {"sortField": "CCY-PROD-CDE", "sortOrder": "+"},
                {"sortField": "PROD-MTUR-DT", "sortOrder": "+"}
            ]
        })
        base_data['holdingAccountInformation']['productDashboardTypeInformation'] = [
            {"productDashboardTypeCode": "UWCASH"}
        ]
        return base_data

    def build_request(self, kind=None):
        return dict(
            url=self.URL,
            data=self.build_request_data(kind=kind),
            headers=self.build_request_headers(),
            cookies=self.build_request_cookies(),
        )

    def build_request_headers(self):
        xsrf_token = self.browser.session.cookies['XSRF-TOKEN']
        return {
            "Content-Type": "application/json;charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            'Accept': '*/*',
            "Connection": "keep-alive",
            "X-HDR-App-Role": "ALL",
            "X-HDR-Target-Function": "currentholdings",
            'X-XSRF-TOKEN': xsrf_token,
        }

    def build_request_cookies(self):
        mandatory_cookies = {
            'opt_in_status': "1",
            'CAMToken': self.browser.session.cookies.get('CAMToken', domain='.investissements.clients.hsbc.fr')
        }
        for key in ('JSESSIONID', 'XSRF-TOKEN', 'WEALTH-FR-CUST-PORTAL-COOKIE'):
            value = self.browser.session.cookies.get(key, domain='investissements.clients.hsbc.fr')
            assert value, key + " cookie is not set"
            mandatory_cookies.update({key: value})

        return mandatory_cookies

    def build_request_data(self, kind=None):
        d = self.browser.SESSION_INFO['app_data'].get('data')
        assert d, 'No Session Data to perform a request'
        localeCode = '_'.join((d['localeLanguage'], d['localeCountry']))
        holdingAccountInformation = {
            'customerNumber': d['customerID'],
            'localeLocalCode': localeCode,
            'transactionRangeEndDate': int(time.time() * 1000),
        }
        baseHeader = {
            'sessionId': d['sessionID'],
            'userDeviceId': d['userDeviceID'],
            'userId': d['userId'],
        }
        request_data = {
            'channelId': d['channelID'],
            'countryCode': d['customerCountryCode'],
            'customerNumber': d['customerID'],
            'frameworkHeader': {
                'customerElectronicBankingChangeableIdentificationNumber': d['userId'],
                'customerElectronicBankingIdentificationNumber': d['userId'],
            },
            'groupMember': d['customerGroupMemberID'],
            'lineOfBusiness': d['customerBusinessLine'],
            'localeCode': localeCode,
            'swhcbApplicationHeader': {
                'hubUserId': d['userLegacyID'],
                'hubWorkstationId': d['userLegacyDeviceID'],
            },
        }
        if kind == 'account_list':
            holdingAccountInformation.update(self.raw_post_data()['holdingAccountInformation'])
            request_data.update(self.raw_post_data())
        elif kind == 'investment_list' or kind == 'liquidity_account':
            """ Build request data to fetch the list of investments """
            request_data.pop("localeCode")

            if kind == 'investment_list':
                holdingAccountInformation.update(self.investment_list_post_data()['holdingAccountInformation'])
                request_data.update(self.investment_list_post_data())

            elif kind == 'liquidity_account':
                holdingAccountInformation.update(self.liquidity_account_post_data()['holdingAccountInformation'])
                request_data.update(self.liquidity_account_post_data())

            if 'req_id' in self.browser.SESSION_INFO:  # update request identification number
                holdingAccountInformation['requestIdentificationNumber'] = self.browser.SESSION_INFO['req_id']

        else:
            raise NotImplementedError()

        # set up common keys for the request
        request_data['holdingAccountInformation'] = holdingAccountInformation
        request_data['baseHeader'] = baseHeader

        return request_data

    def retrieve_products(self, kind=None):
        """ Build the request from scratch according to 'kind' parameter """
        req = self.build_request(kind=kind)
        # self.browser.location(self.browser.SESSION_INFO['app_location'])
        # cookies may be optionals but headers are mandatory.
        self.browser.location(req['url'], method='POST', data=json.dumps(req['data']), headers=req['headers'], cookies=req['cookies'])
        self.browser.SESSION_INFO['req_id'] = self.browser.response.json()['sessionInformation']['requestIdentificationNumber']

    def retrieve_invests(self):
        self.retrieve_products(kind='investment_list')
        assert isinstance(self.browser.page, RetrieveInvestmentsPage)
        return self.browser.page.iter_investments()

    def retrieve_liquidity_account(self):
        self.retrieve_products(kind='liquidity_account')
        assert isinstance(self.browser.page, RetrieveLiquidityPage)
        return self.browser.page.iter_liquidity_accounts()

    def retrieve_accounts(self):
        self.retrieve_products(kind='account_list')
        assert isinstance(self.browser.page, RetrieveAccountsPage)
        return self.browser.page.iter_accounts()


class RetrieveAccountsPage(LoggedPage, JsonPage):

    def is_here(self):
        # We should never have both informations at the same time
        assert bool(self.response.json()['holdingOrderInformation']) != bool(self.response.json()['accountFilterInformation'])
        return bool(self.response.json()['accountFilterInformation'])

    @method
    class iter_accounts(DictElement):
        TYPE_ACCOUNTS = {
            'INVESTMENT': Account.TYPE_PEA,
            'CURRENT': Account.TYPE_CHECKING,
        }

        item_xpath = 'accountGroupInformation'

        class item(ItemElement):

            klass = Account

            def condition(self):
                return len(Dict('accountListInformation')(self)) == 1

            def obj_type(self):
                return self.parent.TYPE_ACCOUNTS.get(Dict(
                    'dashboardAccountSubGroupIdentifier'
                )(self))

            obj_number = CleanText(Dict('accountListInformation/0/accountNumber'))
            obj_id = CleanText(Dict('accountListInformation/0/accountNickName'))
            obj_currency = Currency(Dict('accountListInformation/0/currencyAccountCode'))
            obj_balance = CleanDecimal(
                Dict('accountGroupMultipleCurrencyInformation/0/accountMarketValueAmount')
            )
            obj_valuation_diff = CleanDecimal(
                Dict('accountGroupMultipleCurrencyInformation/0/profitLossUnrealizedAmount'),
                default=NotAvailable
            )


class RetrieveInvestmentsPage(LoggedPage, JsonPage):

    def is_here(self):
        assert bool(self.response.json()['holdingOrderInformation']) != bool(self.response.json()['accountFilterInformation'])
        return (
            bool(self.response.json()['holdingOrderInformation']) and
            self.response.json()['holdingOrderInformation'][0]['accountTypeCode'] != 'OTH'
        )

    @method
    class iter_investments(DictElement):
        item_xpath = 'holdingOrderInformation'

        class item(ItemElement):
            klass = Investment

            obj_label = CleanText(Dict('productName'))
            obj_code = CleanText(Dict('productIdInformation/0/productAlternativeNumber'))
            obj_code_type = Investment.CODE_TYPE_ISIN
            obj_quantity = CleanDecimal(Dict('holdingDetailInformation/0/productHoldingQuantityCount'))
            obj_vdate = Eval(
                lambda x: datetime.datetime.fromtimestamp(x // 1000),
                Dict('holdingDetailInformation/0/productPriceUpdateDate')
            )
            obj_diff = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/0/profitLossUnrealizedAmount'
            ), default=NotAvailable)
            obj_unitprice = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/0/productHoldingUnitCostAverageAmount'
            ), default=NotAvailable)
            obj_unitvalue = CleanDecimal(Dict('holdingDetailInformation/0/productMarketPriceAmount'))
            obj_valuation = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/0/productHoldingMarketValueAmount'
            ), default=NotAvailable)
            obj_diff_percent = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/0'
                '/profitLossUnrealizedPercent'
            ), default=NotAvailable)
            obj_portfolio_share = NotAvailable  # must be computed from the sum of iter_investments
            def obj_original_currency(self):
                currency_text = Dict('holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1/currencyProductHoldingBookValueAmountCode')(self)
                if currency_text:
                    return Currency().filter(currency_text)
                else:
                    return NotAvailable

            obj_original_valuation = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1'
                '/productHoldingBookValueAmount'
            ), default=NotAvailable)
            obj_original_unitvalue = CleanDecimal(Dict('holdingDetailInformation/0/productMarketPriceAmount'))
            obj_original_unitprice = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1/productHoldingUnitCostAverageAmount'
            ), default=NotAvailable)
            obj_original_diff = CleanDecimal(Dict(
                'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1/profitLossUnrealizedAmount'
            ), default=NotAvailable)


class RetrieveLiquidityPage(LoggedPage, JsonPage):

    def is_here(self):
        assert bool(self.response.json()['holdingOrderInformation']) != bool(self.response.json()['accountFilterInformation'])
        return (
            bool(self.response.json()['holdingOrderInformation']) and
            self.response.json()['holdingOrderInformation'][0]['accountTypeCode'] == 'OTH'
        )

    @method
    class iter_liquidity_accounts(DictElement):
        item_xpath = 'holdingOrderInformation'

        class item(ItemElement):
            klass = Account

            def condition(self):
                return Dict('productTypeCode')(self) == 'INVCASH'

            obj_label = CleanText(Dict('productShortName'))
            obj_balance = CleanDecimal(
                Dict(
                    'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1'
                    '/productHoldingMarketValueAmount'

                )
            )
            obj_currency = Currency(
                Dict(
                    'holdingDetailInformation/0/holdingDetailMultipleCurrencyInformation/1'
                    '/currencyProductHoldingMarketValueAmountCode'
                )
            )
            obj_number = CleanText(Dict('productAlternativeNumber'))
            obj_type = Account.TYPE_PEA
            obj_parent = NotAvailable
