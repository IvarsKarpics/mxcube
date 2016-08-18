#
#  Project: MXCuBE
#  https://github.com/mxcube.
#
#  This file is part of MXCuBE software.
#
#  MXCuBE is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  MXCuBE is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with MXCuBE.  If not, see <http://www.gnu.org/licenses/>.

import os
import smtplib
import gevent
import logging

import InstanceServer
#import email.Utils

from PyQt4 import QtGui
from PyQt4 import QtCore

from BlissFramework import Qt4_Icons
from BlissFramework.Utils import Qt4_widget_colors
from BlissFramework.Qt4_BaseComponents import BlissWidget

from HardwareRepository.HardwareRepository import dispatcher
import collections


__category__ = "General"


WANTS_CONTROL_EVENT = QtCore.QEvent.User
class WantsControlEvent(QtCore.QEvent):
    """Descript. :
    """

    def __init__(self, client_id):
        """Descr
        """
        QtCore.QEvent.__init__(self, WANTS_CONTROL_EVENT)
        self.client_id = client_id

START_SERVER_EVENT = QtCore.QEvent.User + 1
class StartServerEvent(QtCore.QEvent):
    """Descript. :
    """
 
    def __init__(self):
        QtCore.QEvent.__init__(self, START_SERVER_EVENT)
        """Descr. 
        """

APP_BRICK_EVENT = QtCore.QEvent.User + 2
class AppBrickEvent(QtCore.QEvent):
    """Descr.
    """

    def __init__(self, brick_name, widget_name, method_name, method_args, master_sync):
        """Descr.
        """
        QtCore.QEvent.__init__(self, APP_BRICK_EVENT)
        self.brick_name = brick_name
        self.widget_name = widget_name
        self.method_name = method_name
        self.method_args = method_args
        self.master_sync = master_sync

APP_TAB_EVENT = QtCore.QEvent.User + 3
class AppTabEvent(QtCore.QEvent):
    """Descr."""
 
    def __init__(self, tab_name, tab_index):
        """Descr."""
        QtCore.QEvent.__init__(self, APP_TAB_EVENT)
        self.tab_name = tab_name
        self.tab_index = tab_index

MSG_DIALOG_EVENT = QtCore.QEvent.User + 4
class MsgDialogEvent(QtCore.QEvent):
    """Descript. :"""

    def __init__(self, icon_type, msg, font_size, callback=None):
        """Descr."""
        QtCore.QEvent.__init__(self, MSG_DIALOG_EVENT)
        self.icon_type = icon_type
        self.msg = msg
        self.font_size = font_size
        self.callback = callback

USER_INFO_DIALOG_EVENT = QtCore.QEvent.User + 5
class UserInfoDialogEvent(QtCore.QEvent):
    """Descript. :    """

    def __init__(self, msg, fromaddrs, toaddrs, subject, is_local, font_size):
        """Descript."""
        QtCore.QEvent.__init__(self, USER_INFO_DIALOG_EVENT)
        self.msg = msg
        self.fromaddrs = fromaddrs
        self.toaddrs = toaddrs
        self.is_local = is_local
        self.subject = subject
        self.font_size = font_size


class Qt4_InstanceListBrick(BlissWidget):
    """
    Descript. :
    """

    LOCATIONS = ("UNKNOWN", "LOCAL", "INHOUSE", "INSITE", "EXTERNAL")
    MODES = ("UNKNOWN", "MASTER", "SLAVE")
    ROLES = ("UNKNOWN", "ACTING_AS_SERVER", "LAUNCHING_SERVER",
             "ACTING_AS_CLIENT", "CONNECTING_TO_SERVER")
    IDS = ("UNKNOWN", "USER", "INHOUSE_USER", "INHOUSE_IMPERSONATION")
    RECONNECT_TIME = 5000

    def __init__(self, *args):
        """
        Descript. :
        """
        BlissWidget.__init__(self, *args)

        # Properties ----------------------------------------------------------
        self.addProperty("giveControlTimeout", "integer", 30)
        self.addProperty("initializeServer", "boolean", False)
        self.addProperty("controlEmails", "string", "")

        # Properties to link hwobj --------------------------------------------
        self.addProperty("hwobj_instance_connection",
                         "string",
                         "/instanceconnection")
        self.addProperty("hwobj_xmlrpc_server", "string", "/xml-rpc-server")
        self.addProperty("hwobj_hutch_trigger", "string", "")

        # Signals ------------------------------------------------------------

        # Slots ---------------------------------------------------------------
        self.defineSlot('setSession', ())

        # Hardware objects ----------------------------------------------------
        self.instance_server_hwobj = None
        self.hutch_trigger_hwobj = None
        self.xmlrpc_server = None

        # Internal values -----------------------------------------------------
        self.give_control_msgbox = None
        self.timeout_left = -1
        self.my_proposal = None
        self.in_control = None
        self.connections = {}
        self.server_icon = Qt4_Icons.load_icon("Home2")
        self.client_icon = Qt4_Icons.load_icon("User2")

        # Graphic elements ----------------------------------------------------
        _main_gbox = QtGui.QGroupBox("Current users", self)

        self.users_listwidget = QtGui.QListWidget(_main_gbox)
        self.users_listwidget.setFixedHeight(50)

        self.give_control_chbox = QtGui.QCheckBox(\
             "Selecting gives control", _main_gbox)
        self.give_control_chbox.setChecked(False)
        self.allow_timeout_control_chbox = QtGui.QCheckBox(\
             "Allow timeout control", _main_gbox)
        self.allow_timeout_control_chbox.setChecked(False)

        self.take_control_button = QtGui.QToolButton(_main_gbox)
        self.take_control_button.setUsesTextLabel(True)
        self.take_control_button.setText("Take control")
        self.take_control_button.setEnabled(True)
        self.take_control_button.setIcon(Qt4_Icons.load_icon("FingerRight"))
        self.take_control_button.hide()

        self.ask_control_button = QtGui.QToolButton(_main_gbox)
        self.ask_control_button.setUsesTextLabel(True)
        self.ask_control_button.setText("Ask for control")
        self.ask_control_button.setEnabled(False)
        self.ask_control_button.setIcon(Qt4_Icons.load_icon("FingerUp"))

        _my_name_widget = QtGui.QWidget(_main_gbox)
        _my_name_label = QtGui.QLabel("My name:", _my_name_widget)
        self.nickname_ledit = NickEditInput(_my_name_widget)

        reg_exp = QtCore.QRegExp(".+")
        nick_validator = QtGui.QRegExpValidator(reg_exp, self.nickname_ledit)
        self.nickname_ledit.setValidator(nick_validator)

        self.external_user_info_dialog = ExternalUserInfoDialog()

        # Layout --------------------------------------------------------------
        _my_name_widget_layout = QtGui.QHBoxLayout(_my_name_widget)
        _my_name_widget_layout.addWidget(_my_name_label)
        _my_name_widget_layout.addWidget(self.nickname_ledit)
        #_my_name_widget_layout.addStretch(0)
        _my_name_widget_layout.setSpacing(2)
        _my_name_widget_layout.setContentsMargins(0, 0, 0, 0)

        _main_gbox_vlayout = QtGui.QVBoxLayout(_main_gbox)
        _main_gbox_vlayout.addWidget(self.users_listwidget)
        _main_gbox_vlayout.addWidget(self.give_control_chbox)
        _main_gbox_vlayout.addWidget(self.allow_timeout_control_chbox)
        _main_gbox_vlayout.addWidget(self.take_control_button)
        _main_gbox_vlayout.addWidget(self.ask_control_button)
        _main_gbox_vlayout.addWidget(_my_name_widget)
        _main_gbox_vlayout.setSpacing(2)
        _main_gbox_vlayout.setContentsMargins(2, 2, 2, 2)

        _main_vlayout = QtGui.QVBoxLayout(self)
        _main_vlayout.addWidget(_main_gbox)
        _main_vlayout.setSpacing(0)
        _main_vlayout.setContentsMargins(2, 2, 2, 2)
 
        # SizePolicies --------------------------------------------------------
        self.ask_control_button.setSizePolicy(QtGui.QSizePolicy.Expanding,
                                              QtGui.QSizePolicy.Fixed)

        # Qt signal/slot connections ------------------------------------------
        self.users_listwidget.itemPressed.connect(self.user_selected)
        self.take_control_button.clicked.connect(self.take_control_clicked)
        self.ask_control_button.clicked.connect(self.ask_for_control_clicked)
        self.nickname_ledit.returnPressed.connect(self.change_my_name)

        # Other ---------------------------------------------------------------
        self.timeout_timer = QtCore.QTimer(self)
        self.timeout_timer.timeout.connect(self.timeout_approaching)


    def propertyChanged(self, property_name, old_value, new_value):
        """
        Descript. :
        """
        if property_name == 'hwobj_instance_connection':
            if self.instance_server_hwobj is not None:
                self.disconnect(self.instance_server_hwobj,
                                'instanceInitializing',
                                self.instance_initializing)
                self.disconnect(self.instance_server_hwobj,
                                'serverInitialized',
                                self.server_initialized)
                self.disconnect(self.instance_server_hwobj,
                                'clientInitialized',
                                self.client_initialized)
                self.disconnect(self.instance_server_hwobj,
                                'serverClosed',
                                self.server_closed)
                self.disconnect(self.instance_server_hwobj,
                                'newClient',
                                self.new_client)
                self.disconnect(self.instance_server_hwobj,
                                'haveControl',
                                self.have_control)
                self.disconnect(self.instance_server_hwobj,
                                'passControl',
                                self.pass_control)
                self.disconnect(self.instance_server_hwobj,
                                'wantsControl',
                                self.wants_control)
                self.disconnect(self.instance_server_hwobj,
                                'widgetUpdate',
                                self.widget_update)
                self.disconnect(self.instance_server_hwobj,
                                'clientChanged',
                                self.client_changed)
                self.disconnect(self.instance_server_hwobj,
                                'clientClosed',
                                self.client_closed)
                self.disconnect(self.instance_server_hwobj,
                                'widgetCall',
                                self.widget_call)

            self.instance_server_hwobj = self.getHardwareObject(new_value)

            if self.instance_server_hwobj is not None:
                self.connect(self.instance_server_hwobj,
                             'instanceInitializing',
                             self.instance_initializing)
                self.connect(self.instance_server_hwobj,
                             'serverInitialized',
                             self.server_initialized)
                self.connect(self.instance_server_hwobj,
                             'clientInitialized',
                             self.client_initialized)
                self.connect(self.instance_server_hwobj,
                             'serverClosed',
                             self.server_closed)
                self.connect(self.instance_server_hwobj,
                             'newClient',
                             self.new_client)
                self.connect(self.instance_server_hwobj,
                             'haveControl',
                             self.have_control)
                self.connect(self.instance_server_hwobj,
                             'passControl',
                             self.pass_control)
                self.connect(self.instance_server_hwobj,
                             'wantsControl',
                             self.wants_control)
                self.connect(self.instance_server_hwobj,
                             'widgetUpdate',
                             self.widget_update)
                self.connect(self.instance_server_hwobj,
                             'clientChanged',
                             self.client_changed)
                self.connect(self.instance_server_hwobj,
                             'clientClosed',
                             self.client_closed)
                self.connect(self.instance_server_hwobj,
                             'widgetCall',
                             self.widget_call)
        elif property_name == "hwobj_xmlrpc_server":
            self.xmlrpc_server = self.getHardwareObject(new_value)
        elif property_name == 'hwobj_hutch_trigger':
            if self.hutch_trigger_hwobj is not None:
                self.disconnect(self.hutch_trigger_hwobj,
                                "hutchTrigger",
                                self.hutch_trigger_changed)
            self.hutch_trigger_hwobj = self.getHardwareObject(new_value)
            if self.hutch_trigger_hwobj is not None:
                self.connect(self.hutch_trigger_hwobj,
                             "hutchTrigger",
                             self.hutch_trigger_changed)
                self.hutch_trigger_changed(\
                     not self.hutch_trigger_hwobj.door_is_interlocked())
        else:
            BlissWidget.propertyChanged(self, property_name, old_value, new_value)

    def hutch_trigger_changed(self, hutch_opened):
        """
        Descript. :
        """
        if hutch_opened:
            if not BlissWidget.isInstanceRoleServer():
                logging.getLogger().info("HUTCH IS OPENED, YOU LOSE CONTROL")
                self.take_control_button.setEnabled(False)
            else:
                logging.getLogger().info("HUTCH IS OPENED, TAKING " + \
                                         "CONTROL OVER REMOTE USERS")
                self.instance_server_hwobj.takeControl()
        else:
            if not BlissWidget.isInstanceRoleServer():
                logging.getLogger().info("HUTCH IS CLOSED, YOU ARE " + \
                                         "ALLOWED TO TAKE CONTROL AGAIN")
                self.take_control_button.setEnabled(True)


    def setSession(self, session_id, prop_code=None, prop_number=None, \
                    prop_id=None, expiration=None, orig_prop_code=None, \
                    is_inhouse=None):
        """
        Descript. :
        """
        self.external_user_info_dialog.clear_user_info()
        if prop_code is not None and prop_number is not None \
        and prop_code != '' and prop_number != '':
            if self.instance_server_hwobj is not None:
                try:
                    proposal_dict = {"code" : orig_prop_code,
                                     "alias" : prop_code,
                                     "number" : prop_number,
                                     "session" : int(session_id),
                                     "inhouse" : is_inhouse}
                except:
                    logging.getLogger().exception(\
                       "InstanceListBrick: problem setting session")
                    return
                else:
                    self.my_proposal = proposal_dict
                    self.instance_server_hwobj.setProposal(proposal_dict)

            if is_inhouse:
                BlissWidget.setInstanceUserId(\
                   BlissWidget.INSTANCE_USERID_INHOUSE)
                self.ask_control_button.hide()
                self.take_control_button.show()
                self.take_control_button.setEnabled(\
                     BlissWidget.isInstanceRoleServer())
                if self.hutch_trigger_hwobj is not None \
                and not BlissWidget.isInstanceModeMaster():
                    hutch_opened = 1 - int(self.hutch_trigger_hwobj.\
                                           door_is_interlocked())
                    logging.getLogger().info(\
                       "Hutch is %s, " % (hutch_opened and \
                       "opened" or "close") +  \
                       "%s 'Take control' button" %(hutch_opened and \
                       "disabling" or "enabling"))
                    self.take_control_button.setEnabled(1 - hutch_opened)
            else:
                BlissWidget.setInstanceUserId(\
                   BlissWidget.INSTANCE_USERID_LOGGED)
                self.take_control_button.hide()
                self.ask_control_button.show()
                self.ask_control_button.setEnabled(\
                     not BlissWidget.isInstanceModeMaster())
        else:
            if self.instance_server_hwobj is not None:
                self.my_proposal = None
                self.instance_server_hwobj.setProposal(None)

            BlissWidget.setInstanceUserId(BlissWidget.INSTANCE_USERID_UNKNOWN)
            self.take_control_button.hide()
            self.ask_control_button.show()
            self.ask_control_button.setEnabled(False)

    def reconnect_to_server(self):
        """
        Descript. :
        """
        self.instance_server_hwobj.reconnect(quiet=True)

    def instance_initializing(self):
        """
        Descript. :
        """
        if self.instance_server_hwobj.isLocal():
            local = BlissWidget.INSTANCE_LOCATION_LOCAL
        else:
            local = BlissWidget.INSTANCE_LOCATION_EXTERNAL
        BlissWidget.setInstanceLocation(local)

        for widget in QtGui.QApplication.allWidgets():
            if hasattr(widget, "configuration"):
                active_window = widget
                break 

        active_window.brickChangedSignal.connect(\
              self.application_brick_changed)
        active_window.tabChangedSignal.connect(\
              self.application_tab_changed)

    def client_initialized(self, connected, server_id=None, my_nickname=None, quiet=False):
        """
        Descript. :
        """
        if connected is None:
            BlissWidget.set_instance_role(BlissWidget.INSTANCE_ROLE_CLIENTCONNECTING)
            BlissWidget.set_instance_mode(BlissWidget.INSTANCE_MODE_SLAVE)
        elif not connected:
            if not quiet:
                msg_event = MsgDialogEvent(\
                    QtGui.QMessageBox.Warning,\
                    "Couldn't connect to the server application!",\
                    self.font().pointSize())
                QtGui.QApplication.postEvent(self, msg_event)
 
            QtCore.QTimer.singleShot(Qt4_InstanceListBrick.RECONNECT_TIME,
                                     self.reconnect_to_server)
        else:
            BlissWidget.set_instance_role(BlissWidget.INSTANCE_ROLE_CLIENT)
            BlissWidget.set_instance_mode(BlissWidget.INSTANCE_MODE_SLAVE)

            server_print = self.instance_server_hwobj.idPrettyPrint(server_id)
            item = QtGui.QListWidgetItem(self.server_icon,
                                         server_print,
                                         self.users_listwidget)
            item.setSelected(False)
            self.nickname_ledit.setText(my_nickname)
            self.connections[server_id[0]] = (item, server_id[1])
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.have_control(False, gui_only=True)
            self.init_name(my_nickname)

            msg_event = MsgDialogEvent(QtGui.QMessageBox.Information,
                "Successfully connected to the server application.",
                self.font().pointSize())
            QtGui.QApplication.postEvent(self, msg_event)

    def server_initialized(self, started, server_id=None):
        """
        Descript. :
        """
        if started:
            BlissWidget.set_instance_role(BlissWidget.INSTANCE_ROLE_SERVER)
            BlissWidget.set_instance_mode(BlissWidget.INSTANCE_MODE_MASTER)
            self.init_name(server_id[0])
            self.have_control(True, gui_only=True)
        else:
            msg_dialog = QtGui.QMessageBox("mxCuBE",\
                "Couldn't start the multiple instances server!",\
                QtGui.QMessageBox.Critical,
                QMessageBox.Ok,
                QMessageBox.NoButton,\
                QtGui.QMessageBox.NoButton,
                self)
            msg_dialog.setButtonText(QtGui.QMessageBox.Ok, "Quit")
            #s=self.font().pointSize()
            #f=msg_dialog.font()
            #f.setPointSize(s)
            #msg_dialog.setFont(f)
            #msg_dialog.updateGeometry()
            msg_dialog.show()
            os._exit(1)

    def server_closed(self, server_id):
        """
        Descript. :
        """
        self.users_listwidget.clear()
        self.connections = {}
        BlissWidget.set_instance_role(\
             BlissWidget.INSTANCE_ROLE_CLIENTCONNECTING)
        BlissWidget.set_instance_mode(\
             BlissWidget.INSTANCE_MODE_SLAVE)

        msg_event = MsgDialogEvent(\
            QtGui.QMessageBox.Warning,\
            "The server application closed the connection!",\
            self.font().pointSize())
        QtGui.QApplication.postEvent(self, msg_event)
        QtCore.QTimer.singleShot(Qt4_InstanceListBrick.RECONNECT_TIME,
                                 self.reconnect_to_server)

    def widget_update(self, timestamp, method, method_args, master_sync=True):
        """
        Descript. :
        """
        print timestamp, method, method_args, master_sync
        if self.instance_server_hwobj.isServer():
            BlissWidget.addEventToCache(timestamp, method, *method_args)
            if not master_sync or BlissWidget.shouldRunEvent():
                try:
                    try:
                        if not master_sync:
                            try:
                                method.__self__.blockSignals(True)
                            except AttributeError:
                                pass
                        
                        method(*method_args)
                    except:
                        pass
                finally:
                    try:
                        method.__self__.blockSignals(False)
                    except AttributeError:
                        pass
        else:
            print method, method.__self__
            method.__self__.blockSignals(True)
            method(*method_args)

            method.__self__.blockSignals(False)
            return

            if not master_sync or BlissWidget.shouldRunEvent():
                try:
                    try:
                        if not master_sync:
                            try:
                                method.__self__.blockSignals(True)
                            except AttributeError:
                                pass
                        method(*method_args)
                    except:
                        pass
                finally:
                    try:
                        method.__self__.blockSignals(False)
                    except AttributeError:
                        pass
            else:
                BlissWidget.addEventToCache(timestamp, method, *method_args)

    def widget_call(self, timestamp, method, method_args):
        """
        Descript. :
        """
        try:
            method(*method_args)
        except:
            logging.getLogger().debug("Problem executing an external call")

    def instance_location_changed(self, loc):
        """
        Descript. :
        """
        logging.getLogger().info("Instance running in %s" % \
              Qt4_InstanceListBrick.LOCATIONS[loc].lower())

    def instance_mode_changed(self, mode):
        """
        Descript. :
        """
        logging.getLogger().info("Instance mode set to %s" % \
             Qt4_InstanceListBrick.MODES[mode].lower())
        self.update_mirroring()

    def application_tab_changed(self, tab_name, tab_index):
        """
        Descript. :
        """
        if self.instance_server_hwobj is not None:
            tab_event = AppTabEvent(tab_name, tab_index)
            QtGui.QApplication.postEvent(self, tab_event)

    def application_brick_changed(self, brick_name, widget_name, \
            method_name, method_args, master_sync):
        """
        Descript. :
        """
        if not master_sync or self.instance_server_hwobj is not None:
            brick_event = AppBrickEvent(brick_name,
                                        widget_name,
                                        method_name,
                                        method_args,
                                        master_sync)
            QtGui.QApplication.postEvent(self, brick_event)

    def init_name(self, new_name):
        """
        Descript. :
        """
        self.nickname_ledit.setText(new_name)
        self.nickname_ledit.acceptInput()

    def change_my_name(self):
        """
        Descript. :
        """
        self.nickname_ledit.setEnabled(False)
        name = str(self.nickname_ledit.text())
        self.instance_server_hwobj.requestIdChange(name)

    def ask_for_control_clicked(self):
        """
        Descript. :
        """ 
        self.instance_server_hwobj.askForControl()

    def take_control_clicked(self):
        """
        Descript. :
        """
        current_user = self.instance_server_hwobj.inControl()
        user_id = current_user[0]
        user_prop = current_user[1]
        control_user_print = self.instance_server_hwobj.idPrettyPrint(current_user)
        take_control_dialog = QtGui.QMessageBox(
            "mxCuBE",\
            "You're about to take control of the application, " + \
            "taking over %s!" % control_user_print,\
            QtGui.QMessageBox.Question, QMessageBox.Ok, QMessageBox.Cancel, \
            QtGui.QMessageBox.NoButton, self)
        take_control_dialog.setButtonText(QtGui.QMessageBox.Ok, "Take control")
        #s=self.font().pointSize()
        #f=take_control_dialog.font()
        #f.setPointSize(s)
        #take_control_dialog.setFont(f)
        #take_control_dialog.updateGeometry()
        if take_control_dialog.exec_() == QtGui.QMessageBox.Ok:
            self.instance_server_hwobj.takeControl()

    def run(self):
        """
        Descript. :
        """
        if self['initializeServer']:
            QtGui.QApplication.postEvent(self, StartServerEvent())

    def instance_user_id_changed(self, user_id):
        """
        Descript. :
        """
        logging.getLogger().info("Instance user identification is %s" % \
             Qt4_InstanceListBrick.IDS[user_id].replace("_", " ").lower())
        self.update_mirroring()

    def instance_role_changed(self, role):
        """
        Descript. :
        """
        logging.getLogger().info("Instance role is %s" % \
            Qt4_InstanceListBrick.ROLES[role].replace("_", " ").lower())
        if role != BlissWidget.INSTANCE_ROLE_UNKNOWN \
        and not self.isVisible():
            self.show()

    def new_client(self, client_id):
        """
        Descript. :
        """
        client_print = self.instance_server_hwobj.idPrettyPrint(client_id)
        item = QtGui.QListWidgetItem(self.client_icon,
                                     client_print,
                                     self.users_listwidget)
        item.setFlags(QtCore.Qt.ItemIsEnabled)
        self.connections[client_id[0]] = (item, client_id[1])

    def client_closed(self, client_id):
        """
        Descript. :
        """
        try:
            item = self.connections[client_id[0]][0]
        except KeyError:
            logging.getLogger().warning('Unknown client has closed (%s)' % \
               str(client_id))
        else:
            self.connections.pop(client_id[0])
            self.users_listwidget.takeItem(self.users_listwidget.row(item))

    def client_changed(self, old_client_id, new_client_id):
        """
        Descript. :
        """
        try:
            item = self.connections[old_client_id[0]][0]
        except KeyError:
            self.nickname_ledit.setText(new_client_id[0])
            self.nickname_ledit.setEnabled(True)
            self.nickname_ledit.acceptInput()
        else:
            new_client_print = self.instance_server_hwobj.\
                idPrettyPrint(new_client_id)
            item.setText(new_client_print)
            if new_client_id[0] != old_client_id[0]:
                self.connections[new_client_id[0]] = \
                    self.connections[old_client_id[0]]
                self.connections.pop(old_client_id[0])
                if self.in_control is not None \
                and old_client_id[0] == self.in_control[0]:
                    self.in_control[0] = new_client_id[0]
            else:
                if self.in_control is not None \
                and old_client_id[0] == self.in_control[0]:
                    self.in_control[1] = new_client_id[1]
                    self.update_mirroring()
            self.users_listwidget.updateGeometries()

    def user_selected(self, item):
        """
        Descript. :
        """
        if item is None:
            return

        if BlissWidget.isInstanceModeMaster() \
        and self.give_control_chbox.isChecked():
            for user_id in self.connections:
                if self.connections[user_id][0] == item:
                    self.instance_server_hwobj.giveControl(\
                         (user_id, self.connections[user_id][1]))
                    break

    def have_control(self, have_control, gui_only=False):
        """
        Descript. :
        """
        camera_brick = None
        for widget in QtGui.QApplication.allWidgets():
            if isinstance(widget, BlissWidget):
                if "CameraBrick" in str(widget.__class__):
                    widget.set_control_mode(have_control)

        if not gui_only:
            if have_control:
                BlissWidget.set_instance_mode(BlissWidget.INSTANCE_MODE_MASTER)
            else:
                BlissWidget.set_instance_mode(BlissWidget.INSTANCE_MODE_SLAVE)

        if have_control:
            if self.xmlrpc_server:
                gevent.spawn_later(1, self.xmlrpc_server.open)

            self.in_control = None
            self.take_control_button.setEnabled(False)
            self.ask_control_button.setEnabled(False)

            self.users_listwidget.setSelectionMode(\
                 QtGui.QAbstractItemView.SingleSelection)
            #self.users_listwidget.setSelectionModel()
            self.users_listwidget.clearSelection()
            for item_index in range(self.users_listwidget.count()):
                self.users_listwidget.item(item_index).\
                     setFlags(QtCore.Qt.ItemIsEnabled)
                #tem.setFlags(QtCore.Qt.NoItemFlags)
            self.users_listwidget.setSelectionMode(\
                QtGui.QAbstractItemView.NoSelection)
        else:
            if self.xmlrpc_server:
                self.xmlrpc_server.close()

            if BlissWidget.isInstanceUserIdLogged():
                self.ask_control_button.setEnabled(True)
            elif BlissWidget.isInstanceUserIdInhouse():
                 if self.hutch_trigger_hwobj is not None:
                     hutch_opened = 1 - int(self.hutch_trigger_hwobj.\
                         door_is_interlocked())
                     logging.getLogger().debug("Hutch is %s, " % hutch_opened and \
                                               "opened" or "close" + \
                                               "%s 'Take control' button" % \
                                               hutch_opened and "disabling" or \
                                               "enabling")
                     self.take_control_button.setEnabled(1 - hutch_opened)
            if BlissWidget.isInstanceRoleServer():
                self.take_control_button.setEnabled(True)

        if not gui_only:
            if have_control:
                try:
                    from_bl = os.environ['SMIS_BEAMLINE_NAME']
                    #user = os.environ['SMIS_BEAMLINE_NAME']
                    #frombl = user.replace(' ','-')
                except (KeyError, TypeError, ValueError, AttributeError):
                    from_bl = 'ID??'
                try:
                    proposal = "%s-%d" % (self.my_proposal["code"],
                                          self.myProposal["number"])
                except:
                    proposal = "unknown"

                is_local = BlissWidget.isInstanceLocationLocal()

                if is_local:
                    control_place = "LOCAL"
                else:
                    control_place = "EXTERNAL"
                email_subject = "[MX REMOTE ACCESS] %s " % from_bl + \
                                "control is %s " % control_place + \
                                "(proposal %s)" % proposal
                email_toaddrs = self["controlEmails"]
                email_fromaddrs = "%s@site-to-be-defined.com" % from_bl

                msg_event = UserInfoDialogEvent(\
                    "I've gained control of the application.", \
                    email_fromaddrs, email_toaddrs, email_subject, is_local, \
                    self.font().pointSize())
                logging.getLogger('user_level_log').warning(\
                    "You have gained control of the application.")
            else:
                msg_event = MsgDialogEvent(QtGui.QMessageBox.Warning, \
                    "I've lost control of the application!",\
                    self.font().pointSize())
                logging.getLogger('user_level_log').warning(\
                    "You have lost control of the application!")

    def pass_control(self, has_control_id):
        """
        Descript. :
        """
        try:
            control_item = self.connections[has_control_id[0]][0]
        except KeyError:
            pass
        else:
            self.users_listwidget.clearSelection()
            #item = self.users_listwidget.item(0)
            for item_index in range(self.users_listwidget.count()):
                self.users_listwidget.item(item_index).setFlags(\
                     QtCore.Qt.ItemIsEnabled)
            self.users_listwidget.setSelectionMode(\
                 QtGui.QAbstractItemView.SingleSelection)
            control_item.setFlags(QtCore.Qt.ItemIsEnabled | \
                                  QtCore.Qt.ItemIsSelectable)
            control_item.setSelected(True)
            self.users_listwidget.setSelectionMode(\
                 QtGui.QAbstractItemView.NoSelection)
            self.in_control = list(has_control_id)
            self.update_mirroring()

    def update_mirroring(self):
        """
        Descript. :
        """
        if BlissWidget.isInstanceModeSlave():
            if BlissWidget.isInstanceUserIdUnknown():
                if BlissWidget.isInstanceRoleServer() \
                and self.in_control is not None \
                and self.in_control[1] is None:
                    BlissWidget.set_instance_mirror(\
                         BlissWidget.INSTANCE_MIRROR_ALLOW)
                else:
                    BlissWidget.set_instance_mirror(\
                         BlissWidget.INSTANCE_MIRROR_PREVENT)
            elif BlissWidget.isInstanceUserIdInhouse():
                BlissWidget.set_instance_mirror(\
                   BlissWidget.INSTANCE_MIRROR_ALLOW)
            else:
                try:
                    control_is_inhouse = self.in_control[1]['inhouse']
                except:
                    control_is_inhouse = False
                if control_is_inhouse or self.in_control[1] is None:
                    BlissWidget.set_instance_mirror(\
                         BlissWidget.INSTANCE_MIRROR_ALLOW)
                else:
                    try:
                        my_prop_codes = [self.my_proposal['code'],
                                         self.myProposal['alias']]
                    except:
                        my_prop_codes = []
                    try:
                        control_prop_codes = [self.in_control[1]['code'],\
                                              self.in_control[1]['alias']]
                    except:
                        control_prop_codes = []
                    mirror = BlissWidget.INSTANCE_MIRROR_PREVENT
                    for code in my_prop_codes:
                        try:
                            control_prop_codes.index(code)
                        except:
                            pass
                        else:
                            mirror = BlissWidget.INSTANCE_MIRROR_ALLOW
                            break
                    for code in control_prop_codes:
                        try:
                            my_prop_codes.index(code)
                        except:
                            pass
                        else:
                            mirror = BlissWidget.INSTANCE_MIRROR_ALLOW
                            break
                    BlissWidget.set_instance_mirror(mirror)
        else:
            BlissWidget.set_instance_mirror(BlissWidget.INSTANCE_MIRROR_PREVENT)

    def timeout_approaching(self):
        """
        Descript. :
        """
        if self.give_control_msgbox is not None:
            if self.timeout_left in (30, 20, 10):
                self.instance_server_hwobj.sendChatMessage(\
                     InstanceServer.ChatInstanceMessage.PRIORITY_LOW,
                     "%s will have control in %d seconds..." % \
                     (self.give_control_msgbox.nickname,
                      self.timeout_left))
            self.timeout_left -= 1
            if self.timeout_left == 0:
                self.give_control_msgbox.done(QtGui.QMessageBox.Yes)
            else:
                self.give_control_msgbox.setButtonText(\
                     QtGui.QMessageBox.Yes,
                     "Allow (%d secs)" % self.timeout_left)

    def event(self, event):
        """
        Descript. :
        """
        if self.isRunning():
            if event.type() == WANTS_CONTROL_EVENT:
                try:
                    client_id = event.client_id
                except:
                    logging.getLogger().exception("Problem in event!")
                else:
                    client_print = self.instance_server_hwobj.idPrettyPrint(client_id)
                    self.give_control_msgbox.nickname = client_print
                    self.give_control_msgbox.setButtonText(\
                         QtGui.QMessageBox.Yes,
                         "Allow (%d secs)" % self.timeout_left)
                    self.give_control_msgbox.setButtonText(\
                         QtGui.QMessageBox.No,
                         "Deny")
                    self.timeout_timer.start(1000)
                    res = self.give_control_msgbox.exec_()
                    self.timeout_timer.stop()

                    if res == QtGui.QMessageBox.Yes:
                        self.instance_server_hwobj.giveControl(client_id)
                    else:
                        self.instance_server_hwobj.sendChatMessage(\
                             InstanceServer.ChatInstanceMessage.PRIORITY_HIGH,
                             "Control denied for %s!" % client_print)
                    self.give_control_msgbox = None

            elif event.type() == START_SERVER_EVENT:
                if self.instance_server_hwobj is not None:
                    self.instance_server_hwobj.initializeInstance()

            elif event.type() == APP_BRICK_EVENT:
                self.instance_server_hwobj.sendBrickUpdateMessage(\
                    event.brick_name,
                    event.widget_name,
                    event.method_name,
                    event.method_args,
                    event.master_sync)

            elif event.type() == APP_TAB_EVENT:
                self.instance_server_hwobj.sendTabUpdateMessage(\
                    event.tab_name,
                    event.tab_index)

            elif event.type() == MSG_DIALOG_EVENT:
                msg_dialog = QtGui.QMessageBox("mxCuBE",\
                    event.msg, event.icon_type, QtGui.QMessageBox.Ok,\
                    QtGui.QMessageBox.NoButton, QtGui.QMessageBox.NoButton,
                    self)
                msg_dialog.exec_()
                if isinstance(event.callback, collections.Callable):
                    event.callback()

            elif event.type() == USER_INFO_DIALOG_EVENT:
                if event.is_local or event.toaddrs == "":
                    msg_dialog = QtGui.QMessageBox("mxCuBE",\
                        event.msg, QtGui.QMessageBox.Information,
                        QtGui.QMessageBox.Ok, QtGui.QMessageBox.NoButton,
                        QtGui.QMessageBox.NoButton, None)
                else:
                    self.external_user_info_dialog.setMessage(event.msg)
                    msg_dialog = self.external_user_info_dialog
                    msg_dialog.show()
                if event.toaddrs != "":
                    if event.is_local:
                        email_body = ""
                    else:
                        user_info = msg_dialog.get_user_info()
                        if user_info["usersInESRF"] is True:
                            users_in_esrf = "yes"
                        elif user_info["usersInESRF"] is False:
                            users_in_esrf = "no"
                        else:
                            users_in_esrf = "not sure..."
                        email_body = \
                           "User name    : %s\n" % user_info["name"] + \
                           "Institute    : %s\n" % user_info["institute"] + \
                           "Telephone    : %s\n" % user_info["phone"]+ \
                           "Email address: %s\n" % user_info["email"]+ \
                                     "Users at ESRF: %s" %  users_in_esrf
                    email_date = email.Utils.formatdate(localtime=True)
                    toaddrs = event.toaddrs.replace(' ', ',')
                    email_message = "From: %s\r\n" % event.fromaddrs + \
                                    "To: %s\r\n" % toaddrs + \
                                    "Subject: %s\r\n" % event.subject + \
                                    "Date: %s\r\n\r\n" % email_date + \
                                    "%s" % email_body
                    logging.getLogger().debug("Sending email from %s to %s" % \
                                              (event.fromaddrs, toaddrs))
                    try:
                        smtp = smtplib.SMTP('smtp', smtplib.SMTP_PORT)
                        smtp.sendmail(event.fromaddrs,
                                      toaddrs.split(','),
                                      email_message)
                    except smtplib.SMTPException as e:
                        logging.getLogger().error("Could not send mail")
                        smtp.quit()
                    else:
                        smtp.quit()
        return QtGui.QWidget.event(self, event)

    def wants_control(self, client_id):
        """
        Descript. :
        """
        if BlissWidget.isInstanceModeMaster() \
        and self.give_control_msgbox is None \
        and self.allow_timeout_control_chbox.isChecked():
            self.timeout_left = self['giveControlTimeout']
            client_print = self.instance_server_hwobj.idPrettyPrint(client_id)
            self.give_control_msgbox = QtGui.QMessageBox(
                "Pass control", \
                "The user %s wants to have control " % client_print + \
                "of the application!", \
                QtGui.QMessageBox.Question,
                QtGui.QMessageBox.Yes,
                QtGui.QMessageBox.No,\
                QtGui.QMessageBox.NoButton,
                self)
            custom_event = WantsControlEvent(client_id)
            QtGui.QApplication.postEvent(self, custom_event)

class LineEditInput(QtGui.QLineEdit):
    """
    Descript: Single-line input field. Changes color depending on the validity
              of the input: red for invalid (or whatever DataCollectBrick2.
                                PARAMETER_STATE["INVALID"] has)
                            white for valid (or whatever DataCollectBrick2.
                                PARAMETER_STATE["OK"]).
    Type       : class (qt.QtGui.QLineEdit)
    API        : setReadOnly(readonly<bool>)
                 <string> text()
    Signals    : returnPressed(),
                 inputValid(valid<bool>),
                 textChanged(txt<string>)
    Notes      : Returns 1/3 of the width in the sizeHint from QtGui.QLineEdit
    """

    PARAMETER_STATE = {"INVALID" : QtCore.Qt.red, \
                       "OK" : QtCore.Qt.white, \
                       "WARNING" : QtCore.Qt.yellow}

    def __init__(self, parent):
        """
        Descript. :
        """
        QtGui.QLineEdit.__init__(self, parent)
        self.textChanged.connect(self.text_changed)
        self.returnPressed.connect(self.return_pressed)
        self.colorDefault = None
        self.origPalette = QtGui.QPalette(self.palette())
        self.palette2 = QtGui.QPalette(self.origPalette)
        self.palette2.setColor(\
             QtGui.QPalette.Active,
             QtGui.QPalette.Base, 
             self.origPalette.brush(QtGui.QPalette.Disabled,
                                    QtGui.QPalette.Background).color())
        self.palette2.setColor(\
             QtGui.QPalette.Inactive,
             QtGui.QPalette.Base,
             self.origPalette.brush(QtGui.QPalette.Disabled,
                                    QtGui.QPalette.Background).color())
        self.palette2.setColor(\
             QtGui.QPalette.Disabled,
             QtGui.QPalette.Base,
             self.origPalette.brush(QtGui.QPalette.Disabled,
                                    QtGui.QPalette.Background).color())

    def return_pressed(self):
        """
        Descript. :
        """
        if self.validator() is not None:
            if self.hasAcceptableInput():
                self.emit(QtCore.SIGNAL("returnPressed"))
        else:
            self.emit(QtCore.SIGNAL("returnPressed"))

    def text(self):
        """
        Descript. :
        """
        return str(QtGui.QLineEdit.text(self))

    def text_changed(self, txt):
        """
        Descript. :
        """
        txt = str(txt)
        valid = None
        if self.validator() is not None:
            if self.hasAcceptableInput():
                valid = True
                if txt == "":
                    if self.colorDefault is None:
                        color = LineEditInput.PARAMETER_STATE["OK"]
                    else:
                        color = self.colorDefault
                else:
                    color = LineEditInput.PARAMETER_STATE["OK"]
            else:
                if txt == "":
                    if self.colorDefault is None:
                        valid = False
                        color = LineEditInput.PARAMETER_STATE["INVALID"]
                    else:
                        color = self.colorDefault
                else:
                    valid = False
                    color = LineEditInput.PARAMETER_STATE["INVALID"]
            Qt4_widget_colors.set_widget_color(self, color)
        else:
            if txt == "":
                if self.colorDefault is None:
                    if self.isReadOnly():
                        color = self.origBackgroundColor()
                    else:
                        color = LineEditInput.PARAMETER_STATE["OK"]
                else:
                    color = self.colorDefault
            else:
                if self.isReadOnly():
                    color = self.origBackgroundColor()
                else:
                    color = LineEditInput.PARAMETER_STATE["OK"]
            self.setPaletteBackgroundColor(color)
        self.emit(QtCore.SIGNAL("textChanged"), txt)
        if valid is not None:
            self.emit(QtCore.SIGNAL("inputValid"), self, valid)

    def sizeHint(self):
        """
        Descript. :
        """
        size_hint = QtGui.QLineEdit.sizeHint(self)
        size_hint.setWidth(size_hint.width() / 3)
        return size_hint

    def setReadOnly(self, readonly):
        """
        Descript. :
        """
        if readonly:
            self.setPalette(self.palette2)
        else:
            self.setPalette(self.origPalette)
        QtGui.QLineEdit.setReadOnly(self, readonly)

    def origBackgroundColor(self):
        """
        Descript. :
        """
        return self.origPalette.disabled().background()

    def setDefaultColor(self, color=None):
        """
        Descript. :
        """
        self.colorDefault = color
        self.txtChanged(self.text())


class NickEditInput(LineEditInput):
    """
    """

    def txtChanged(self, txt):
        """
        Descript. :
        """
        txt = str(txt)
        valid = None
        if self.validator() is not None:
            if self.hasAcceptableInput():
                valid = True
                Qt4_widget_colors.set_widget_color(\
                   self,
                   LineEditInput.PARAMETER_STATE["WARNING"],
                   QtGui.QPalette.Base)
            else:
                valid = False
                Qt4_widget_colors.set_widget_color(\
                   self,
                   LineEditInput.PARAMETER_STATE["INVALID"],
                   QtGui.QPalette.Base)
        self.emit(QtCore.SIGNAL("textChanged"), txt)
        if valid is not None:
            self.emit(QtCore.SIGNAL("inputValid"), self, valid)

    def acceptInput(self):
        """
        Descript. :
        """
        Qt4_widget_colors.set_widget_color(\
            self,
            LineEditInput.PARAMETER_STATE["OK"],
            QtGui.QPalette.Base)

class ExternalUserInfoDialog(QtGui.QDialog):
    """
    """

    def __init__(self):
        """
        """
        QtGui.QDialog.__init__(self, None)
        self.setWindowTitle('mxCuBE')

        # Hardware objects ----------------------------------------------------

        # Internal values -----------------------------------------------------

        # Properties ----------------------------------------------------------

        # Signals -------------------------------------------------------------

        # Slots ---------------------------------------------------------------

        # Graphic elements ----------------------------------------------------
        self.message_box = QtGui.QGroupBox("Your info", self) #v
        self.message1 = QtGui.QLabel(self.message_box)
        self.message2 = QtGui.QLabel("<nobr>Please enter the following " + \
                                     "information, <u>required</u> for " + \
                                     "the experimental hall operator:",
                                     self.message_box)
        my_name_widget = QtGui.QWidget(self.message_box)
        name_label = QtGui.QLabel("Your name:", my_name_widget)
        self.name_input = QtGui.QLineEdit(my_name_widget)
        institute_label = QtGui.QLabel("Your institute:", my_name_widget)
        self.institute_input = QtGui.QLineEdit(my_name_widget)
        phone_label = QtGui.QLabel("Your telephone:", my_name_widget)
        self.phone_input = QtGui.QLineEdit(my_name_widget)
        email_label = QtGui.QLabel("Your email:", my_name_widget)
        self.email_input = QtGui.QLineEdit(my_name_widget)

        # Layout --------------------------------------------------------------

        # SizePolicies --------------------------------------------------------
        self.message_box.setSizePolicy(QtGui.QSizePolicy.MinimumExpanding,
                                      QtGui.QSizePolicy.Fixed)

        # Qt signal/slot connections ------------------------------------------

        # Other ---------------------------------------------------------------
        _my_name_widget_vlayout = QtGui.QVBoxLayout(my_name_widget)
        _my_name_widget_vlayout.addWidget(name_label)
        _my_name_widget_vlayout.addWidget(self.name_input)
        _my_name_widget_vlayout.addWidget(institute_label)
        _my_name_widget_vlayout.addWidget(self.institute_input)
        _my_name_widget_vlayout.addWidget(phone_label)
        _my_name_widget_vlayout.addWidget(self.phone_input)
        _my_name_widget_vlayout.addWidget(email_label)
        _my_name_widget_vlayout.addWidget(self.email_input)

        _message_gbox_vlayout = QtGui.QVBoxLayout(self.message_box)
        _message_gbox_vlayout.addWidget(self.message1)
        _message_gbox_vlayout.addWidget(self.message2)
        _message_gbox_vlayout.addWidget(my_name_widget)

        main_layout = QtGui.QVBoxLayout(self)
        main_layout.addWidget(self.message_box)
        main_layout.setSpacing(0)
        #main_layout.addWidget(self.buttons_box)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.name_input.textChanged.connect(self.validate_parameters)
        self.institute_input.textChanged.connect(self.validate_parameters)
        self.phone_input.textChanged.connect(self.validate_parameters)
        self.email_input.textChanged.connect(self.validate_parameters)

    def show(self):
        self.validate_parameters()
        return QtGui.QDialog.exec_(self)

    def validate_parameters(self):
        if len(str(self.name_input.text())) \
        and len(str(self.institute_input.text())) \
        and len(str(self.phone_input.text())) \
        and len(str(self.email_input.text())):
            self.buttons_box.setEnabled(True)
        else:
            self.buttons_box.setEnabled(False)

    def buttonClicked(self, text):
        self.accept()

    def setMessage(self, msg):
        self.message1.setText("<b>%s</b>" % msg)

    def clear_user_info(self):
        self.name_input.setText("")
        self.institute_input.setText("")
        self.phone_input.setText("")
        self.email_input.setText("")

    def get_user_info(self):
        user_info_dict = {"name" : str(self.name_input.text()), \
                          "institute" : str(self.institute_input.text()), \
                          "phone" : str(self.phone_input.text()), \
                          "email" : str(self.email_input.text()), \
                          "usersInESRF": False}
        return user_info_dict
