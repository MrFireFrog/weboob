# -*- coding: utf-8 -*-

# Copyright(C) 2017      Roger Philibert
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

from __future__ import unicode_literals

from weboob.browser.elements import ItemElement, ListElement, method
from weboob.browser.filters.standard import CleanText, Duration, Regexp, Env, Field, RawText, Eval, Base
from weboob.browser.filters.html import AbsoluteLink, Attr
from weboob.browser.filters.json import Dict
from weboob.browser.pages import HTMLPage, pagination
from weboob.capabilities.video import BaseVideo
from weboob.capabilities.image import Thumbnail
from weboob.tools.json import json


class VideoPage(HTMLPage):
    @method
    class get_video(ItemElement):
        klass = BaseVideo

        obj_nsfw = True
        obj_ext = 'mp4'
        obj_title = Attr('//meta[@property="og:title"]', 'content')
        obj_id = Env('id')

        obj__props = Eval(json.loads, Regexp(RawText('//script[contains(text(),"XPlayerTPL2")]'), r'XPlayerTPL2\(\n[^\n]+\n(.*),\n'))

        obj_duration = Base(Field('_props'), Dict('duration'))
        obj_url = Base(Field('_props'), Dict('sources/mp4/0/url'))

        def obj__page(self):
            return self.page.url


class SearchPage(HTMLPage):
    @pagination
    @method
    class iter_videos(ListElement):
        next_page = AbsoluteLink('//a[text()="Suivant"]')
        item_xpath = '//div[@class="video"]'

        class item(ItemElement):
            klass = BaseVideo

            obj_nsfw = True
            obj_ext = 'mp4'

            obj_title = CleanText('./a/u')
            obj_duration = Duration(CleanText('./a/b'))
            obj__page = AbsoluteLink('./a')
            obj_id = Regexp(obj__page, r'/videos/(.+)')

            def obj_thumbnail(self):
                return Thumbnail(Attr('.//img[@class="thumb"]', 'src')(self))
