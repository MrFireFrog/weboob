# -*- coding: utf-8 -*-

# Copyright(C) 2013 Julien Veyssier
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

from PyQt4.QtGui import QFrame

from weboob.applications.qcineoob.ui.minisubtitle_ui import Ui_MiniSubtitle
from weboob.capabilities.base import empty


class MiniSubtitle(QFrame):
    def __init__(self, weboob, backend, subtitle, parent=None):
        QFrame.__init__(self, parent)
        self.parent = parent
        self.ui = Ui_MiniSubtitle()
        self.ui.setupUi(self)

        self.weboob = weboob
        self.backend = backend
        self.subtitle = subtitle
        self.ui.nameLabel.setText(subtitle.name)
        if not empty(subtitle.nb_cd):
            self.ui.nbcdLabel.setText(u'%s'%subtitle.nb_cd)
        self.ui.backendLabel.setText(backend.name)

    def enterEvent(self, event):
        self.setFrameShadow(self.Sunken)
        QFrame.enterEvent(self, event)

    def leaveEvent(self, event):
        self.setFrameShadow(self.Raised)
        QFrame.leaveEvent(self, event)

    def mousePressEvent(self, event):
        QFrame.mousePressEvent(self, event)

        subtitle = self.backend.get_subtitle(self.subtitle.id)
        if subtitle:
            self.parent.doAction('Details of subtitle "%s"'%subtitle.name,self.parent.displaySubtitle,[subtitle,self.backend])
