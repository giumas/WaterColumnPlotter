# Lynette Davis
# Center for Coastal and Ocean Mapping
# November 2021

from PyQt5 import QtWidgets, uic
from PyQt5.QtGui import QIntValidator, QRegExpValidator
from PyQt5.QtCore import pyqtSignal, QRegExp
import sys

import ipaddress

__appname__ = "Settings Dialog"

class AllSettingsDialog2(QtWidgets.QDialog):

    signalSystemEdited = pyqtSignal(name="systemEdited")
    signalIPEdited = pyqtSignal(name="ipEdited")
    signalPortEdited = pyqtSignal(name="portEdited")
    signalBinSizeEdited = pyqtSignal(name="binSizeEdited")
    signalAcrossTrackAvgEdited = pyqtSignal(name="acrossTrackAvgEdited")
    signalDepthEdited = pyqtSignal(name="depthEdited")
    signalDepthAvgEdited = pyqtSignal(name="depthAvgEdited")
    signalAlongTrackAvgEdited = pyqtSignal(name="alongTrackAvgEdited")
    signalDualSwathPolicyEdited = pyqtSignal(name="dualSwathPolicyEdited")

    def __init__(self, settings, parent=None):
        super(AllSettingsDialog2, self).__init__(parent)

        self.settings = settings

        self.ui = uic.loadUi('Dialogs/UIFiles/AllSettingsDialog.ui', self)
        # Disable ability to resize settings window
        #self.setFixedSize(self.size())

        #self.setDefaultValues()
        self.setValues()

        # Preventative validation:
        self.VALID_PORT_MIN = 1
        self.VALID_PORT_MAX = 65535
        self.setValidators()

    def setValidators(self):
        """
        Enables preventative validation to ensure valid entries in select fields of setting dialog.
        """
        # Preventative validation:

        # IP
        ipRange = "(?:[0-1]?[0-9]?[0-9]|2[0-4][0-9]|25[0-5])"
        ipRegex = QRegExp("^" + ipRange + "\\." + ipRange + "\\." + ipRange + "\\." + ipRange + "$")
        ipValidator = QRegExpValidator(ipRegex, self)
        self.ui.lineEditIP.setValidator(ipValidator)

        # Port
        # TODO: For some reason this is allowing 5-digit integers greater than 65535...
        portValidator = QIntValidator(self.VALID_PORT_MIN, self.VALID_PORT_MAX, self)
        self.ui.lineEditPort.setValidator(portValidator)

    def done(self, i):
        """
        Overriding done() method of QDialog.
        Based on this solution: https://www.qtcentre.org/threads/8048-Validate-Data-in-QDialog
        :param i: 0 when 'Cancel' clicked; 1 when 'OK' clicked.
        """
        # print("done")
        if QtWidgets.QDialog.Accepted == i:  # OK clicked
            if self.validateAndSetValuesFromDialog():
                QtWidgets.QDialog.done(self, i)
            else:
                pass
        else:  # Cancel / Close clicked
            QtWidgets.QDialog.done(self, i)

    def setValues(self):
        """
        Assigns values in self.settings (current settings) to fields in settings dialog.
        *** NOTE: There is no error checking in this method!
        If settings are changed, make sure they are correct / valid at time of change! ***
        """
        # System Settings:
        if self.settings['system_settings']['system'] == "Kongsberg":
            self.ui.radioButtonKongsberg.setChecked(True)
        else:
            self.ui.radioButtonOther.setChecked(True)
            self.ui.lineEditOther.setText(self.settings['system_settings']['system'])

        # IP Settings:
        self.ui.lineEditIP.setText(self.settings['ip_settings']['ip'])
        self.ui.lineEditPort.setText(str(self.settings['ip_settings']['port']))

        # Processing Settings:
        self.ui.doubleSpinBoxBinSize.setValue(round(self.settings['processing_settings']['binSize_m'], 2))
        self.ui.doubleSpinBoxAcrossTrackAvg.setValue(round(self.settings['processing_settings']['acrossTrackAvg_m'], 2))
        self.ui.doubleSpinBoxDepth.setValue(round(self.settings['processing_settings']['depth_m'], 2))
        self.ui.doubleSpinBoxDepthAvg.setValue(round(self.settings['processing_settings']['depthAvg_m'], 2))
        self.ui.spinBoxAlongTrackAvg.setValue(self.settings['processing_settings']['alongTrackAvg_ping'])
        if self.settings['processing_settings']['dualSwathPolicy'] == 0:
            self.ui.radioButtonAllPings.setChecked(True)
        elif self.settings['processing_settings']['dualSwathPolicy'] == 1:
            self.ui.radioButtonFirstPing.setChecked(True)
        elif self.settings['processing_settings']['dualSwathPolicy'] == 2:
            self.ui.radioButtonSecondPing.setChecked(True)

    def validateAndSetValuesFromFile(self, loadSettings):
        """
        Assigns values in loadSettings to fields in settings dialog and self.settings; emits signals for changed fields.
        :param loadedSettings: A python dictionary of the same format as self.settings,
        containing settings loaded from a file.
        """
        print("validateAndSetValuesFromFile")
        systemEdited = False
        ipEdited = False
        portEdited = False
        binSizeEdited = False
        acrossTrackAvgEdited = False
        depthEdited = False
        depthAvgEdited = False
        alongTrackAvgEdited = False
        dualSwathPolicyEdited = False

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # System Settings:

        # If system value has changed:
        if self.settings['system_settings']['system'] != loadSettings['system_settings']['system']:

            # TODO: Enable these lines when additional systems supported:
            # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
            # self.settings['system_settings']['system'] = loadSettings['system_settings']['system']
            # if self.settings['system_settings']['system'] == "Kongsberg":
            #     self.ui.radioButtonKongsberg.setChecked(True)
            # else:
            #     self.ui.radioButtonOther.setChecked(True)
            #     self.ui.lineEditOther.setText(self.settings['system_settings']['system'])
            # systemEdited = True
            # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

            # TODO: Disable these lines when additional systems supported:
            # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
            if loadSettings['system_settings']['system'] == "Kongsberg":
                self.settings['system_settings']['system'] = loadSettings['system_settings']['system']
                self.ui.radioButtonKongsberg.setChecked(True)
                systemEdited = True
            else:
                self.settings['system_settings']['system'] = "Kongsberg"
                self.ui.radioButtonKongsberg.setChecked(True)
                QtWidgets.QMessageBox.warning(self, "Warning", "Currently supporting only Kongsberg systems.")
            # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # IP Settings:

        # If IP value has changed:
        if self.settings['ip_settings']['ip'] != loadSettings['ip_settings']['ip']:
            try:
                # Check for valid IP address:
                ipaddress.ip_address(loadSettings['ip_settings']['ip'])
                self.settings['ip_settings']['ip'] = loadSettings['ip_settings']['ip']
                self.ui.lineEditIP.setText(self.settings['ip_settings']['ip'])
                ipEdited = True
            except ValueError:
                # NOTE: This is activated when nothing or incomplete IP address is entered!
                self.ui.lineEditIP.setText(self.settings['ip_settings']['ip'])
                QtWidgets.QMessageBox.warning(self, "Warning", "Invalid IP address."
                                                               "\nIP reset to {}."
                                              .format(self.settings['ip_settings']['ip']))

        # If port value has changed:
        if self.settings['ip_settings']['port'] != loadSettings['ip_settings']['port']:
            try:
                self.settings['ip_settings']['port'] = int(loadSettings['ip_settings']['port'])
                self.ui.lineEditPort.setText(str(self.settings['ip_settings']['port']))
                portEdited = True
            except ValueError:
                # NOTE: This is still activated when nothing is entered!
                self.ui.lineEditPort.setText(str(self.settings['ip_settings']['port']))
                QtWidgets.QMessageBox.warning(self, "Warning", "Invalid port number."
                                                               "\nPort reset to {}."
                                              .format(str(self.settings['ip_settings']['port'])))

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Processing Settings:

        # bin_size_m
        if self.settings['processing_settings']['binSize_m'] != \
                loadSettings['processing_settings']['binSize_m']:

            self.settings['processing_settings']['binSize_m'] = \
                loadSettings['processing_settings']['binSize_m']
            self.ui.doubleSpinBoxBinSize.setValue(self.settings['processing_settings']['binSize_m'])
            binSizeEdited = True

        # acrossTrackAvg_m
        if self.settings['processing_settings']['acrossTrackAvg_m'] != \
                loadSettings['processing_settings']['acrossTrackAvg_m']:

            self.settings['processing_settings']['acrossTrackAvg_m'] = \
                loadSettings['processing_settings']['acrossTrackAvg_m']
            self.ui.doubleSpinBoxAcrossTrackAvg.setValue(self.settings['processing_settings']['acrossTrackAvg_m'])
            acrossTrackAvgEdited = True

        if self.settings['processing_settings']['depth_m'] != \
                loadSettings['processing_settings']['depth_m']:

            self.settings['processing_settings']['depth_m'] = \
                loadSettings['processing_settings']['depth_m']
            self.ui.doubleSpinBoxDepth.setValue(self.settings['processing_settings']['depth_m'])
            depthEdited = True

        # depthAvg_m:
        if self.settings['processing_settings']['depthAvg_m'] != \
                loadSettings['processing_settings']['depthAvg_m']:

            self.settings['processing_settings']['depthAvg_m'] = \
                loadSettings['processing_settings']['depthAvg_m']
            self.ui.doubleSpinBoxDepthAvg.setValue(self.settings['processing_settings']['depthAvg_m'])
            depthAvgEdited = True

        # alongTrackAvg_ping:
        if self.settings['processing_settings']['alongTrackAvg_ping'] != \
                loadSettings['processing_settings']['alongTrackAvg_ping']:

            self.settings['processing_settings']['alongTrackAvg_ping'] = \
                loadSettings['processing_settings']['alongTrackAvg_ping']
            self.ui.doubleSpinBoxAlongTrackAvg.setValue(self.settings['processing_settings']['alongTrackAvg_ping'])
            alongTrackAvgEdited = True

        # dualSwathPolicy (0 to keep all pings; 1 to keep first ping only; 2 to keep second ping only):
        if self.settings['processing_settings']['dualSwathPolicy'] != \
                loadSettings['processing_settings']['dualSwathPolicy']:

            self.settings['processing_settings']['dualSwathPolicy'] = \
                loadSettings['processing_settings']['dualSwathPolicy']
            if self.settings['processing_settings']['dualSwathPolicy'] == 0:
                self.ui.radioButtonAllPings.setChecked(True)
            elif self.settings['processing_settings']['dualSwathPolicy'] == 1:
                self.ui.radioButtonFirstPing.setChecked(True)
            elif self.settings['processing_settings']['dualSwathPolicy'] == 2:
                self.ui.radioButtonSecondPing.setChecked(True)
            dualSwathPolicyEdited = True

        # Only emit signals after all values in dictionary have been updated:
        self.emitSignals(systemEdited, ipEdited, portEdited, binSizeEdited, acrossTrackAvgEdited, depthEdited,
                         depthAvgEdited, alongTrackAvgEdited, dualSwathPolicyEdited)

    def validateAndSetValuesFromDialog(self):
        """
        Assigns values in settings dialog to self.settings; emits signals for changed fields.
        """

        systemEdited = False
        ipEdited = False
        portEdited = False
        binSizeEdited = False
        acrossTrackAvgEdited = False
        depthEdited = False
        depthAvgEdited = False
        alongTrackAvgEdited = False
        dualSwathPolicyEdited = False


        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # System Settings:
        # If system value has changed:
        if self.ui.radioButtonKongsberg.isChecked() and self.settings['system_settings']['system'] != "Kongsberg":
            self.settings['system_settings']['system'] = "Kongsberg"
            systemEdited = True

        # TODO: Enable these lines when additional systems supported:
        # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
        # elif self.ui.radioButtonOther.isChecked() and self.settings['system_settings']['system'] != self.ui.lineEditOther.text():
            # self.settings['system_settings']['system'] = self.ui.lineEditOther.text()
            # systemEdited = True
        # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

        # TODO: Disable these lines when additional systems supported:
        # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
        elif self.ui.radioButtonOther.isChecked():
            self.ui.radioButtonKongsberg.setChecked(True)
            QtWidgets.QMessageBox.warning(self, "Warning", "Currently supporting only Kongsberg systems.")
            return False
        # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # IP Settings:
        # If IP value has changed:
        if self.settings['ip_settings']['ip'] != self.ui.lineEditIP.text():
            try:
                # Check for valid IP address:
                ipaddress.ip_address(self.lineEditIP.text())
                self.settings['ip_settings']['ip'] = self.lineEditIP.text()
                ipEdited = True
            except ValueError:
                # (NOTE: This should be avoided with preventative validation.)
                # TODO: (NOTE: This is still activated when nothing or incomplete IP address is entered!)
                self.ui.lineEditIP.setText(self.settings['ip_settings']['ip'])
                QtWidgets.QMessageBox.warning(self, "Warning", "Invalid IP address."
                                                               "\nIP reset to {}."
                                              .format(self.settings['ip_settings']['ip']))
                return False

        # If port value has changed:
        if self.settings['ip_settings']['port'] != self.ui.lineEditPort.text():
            try:
                self.settings['ip_settings']['port'] = int(self.lineEditPort.text())
                portEdited = True
            except ValueError:
                # (NOTE: This should be avoided with preventative validation.)
                # TODO: (NOTE: This is still activated when nothing is entered!)
                self.ui.lineEditPort.setText(str(self.settings['ip_settings']['port']))
                QtWidgets.QMessageBox.warning(self, "Warning", "Invalid port number."
                                                               "\nPort reset to {}."
                                              .format(str(self.settings['ip_settings']['port'])))
                return False

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Processing Settings:

        # bin_size_m
        if self.settings['processing_settings']['binSize_m'] != self.ui.doubleSpinBoxBinSize.value():
            self.settings['processing_settings']['binSize_m'] = \
                round(self.ui.doubleSpinBoxBinSize.value(), 2)
            binSizeEdited = True

        # acrossTrackAvg_m
        if self.settings['processing_settings']['acrossTrackAvg_m'] != self.ui.doubleSpinBoxAcrossTrackAvg.value():
            self.settings['processing_settings']['acrossTrackAvg_m'] = \
                round(self.ui.doubleSpinBoxAcrossTrackAvg.value(), 2)
            acrossTrackAvgEdited = True

        # depth_m:
        if self.settings['processing_settings']['depth_m'] != self.ui.doubleSpinBoxDepth.value():
            self.settings['processing_settings']['depth_m'] = \
                round(self.ui.doubleSpinBoxDepth.value(), 2)
            depthEdited = True

        # depthAvg_m:
        if self.settings['processing_settings']['depthAvg_m'] != self.ui.doubleSpinBoxDepthAvg.value():
            self.settings['processing_settings']['depthAvg_m'] = \
                round(self.ui.doubleSpinBoxDepthAvg.value(), 2)
            depthAvgEdited = True

        # alongTrackAvg_ping:
        if self.settings['processing_settings']['alongTrackAvg_ping'] != self.ui.spinBoxAlongTrackAvg.value():
            self.settings['processing_settings']['alongTrackAvg_ping'] = \
                int(self.ui.spinBoxAlongTrackAvg.value())
            alongTrackAvgEdited = True

        # dualSwathPolicy (0 to keep all pings; 1 to keep first ping only; 2 to keep second ping only):
        if self.radioButtonAllPings.isChecked() and self.settings['processing_settings']['dualSwathPolicy'] != 0:
            self.settings['processing_settings']['dualSwathPolicy'] = 0
            dualSwathPolicyEdited = True
        elif self.radioButtonFirstPing.isChecked() and self.settings['processing_settings']['dualSwathPolicy'] != 1:
            self.settings['processing_settings']['dualSwathPolicy'] = 1
            dualSwathPolicyEdited = True
        elif self.radioButtonSecondPing.isChecked() and self.settings['processing_settings']['dualSwathPolicy'] != 2:
            self.settings['processing_settings']['dualSwathPolicy'] = 2
            dualSwathPolicyEdited = True

        # Only emit signals after all values in dictionary have been updated:
        self.emitSignals(systemEdited, ipEdited, portEdited, binSizeEdited, acrossTrackAvgEdited, depthEdited,
                         depthAvgEdited, alongTrackAvgEdited, dualSwathPolicyEdited)

        return True

    def emitSignals(self, systemEdited, ipEdited, portEdited, binSizeEdited, acrossTrackAvgEdited, depthEdited,
                    depthAvgEdited, alongTrackAvgEdited, dualSwathPolicyEdited):
        """
        Emits signals for all True parameters.
        :param systemEdited: Boolean indicating whether field was edited.
        :param ipEdited: Boolean indicating whether field was edited.
        :param portEdited: Boolean indicating whether field was edited.
        :param binSizeEdited: Boolean indicating whether field was edited.
        :param acrossTrackAvgEdited: Boolean indicating whether field was edited.
        :param depthEdited: Boolean indicating whether field was edited.
        :param depthAvgEdited: Boolean indicating whether field was edited.
        :param alongTrackAvgEdited: Boolean indicating whether field was edited.
        :param dualSwathPolicyEdited: Boolean indicating whether field was edited.
        """
        if systemEdited:
            self.systemEdited.emit()
        if ipEdited:
            self.ipEdited.emit()
        if portEdited:
            self.portEdited.emit()
        if binSizeEdited:
            print("binsizeedited")
            self.binSizeEdited.emit()
        if acrossTrackAvgEdited:
            self.acrossTrackAvgEdited.emit()
        if depthEdited:
            self.depthEdited.emit()
        if depthAvgEdited:
            self.depthAvgEdited.emit()
        if alongTrackAvgEdited:
            self.alongTrackAvgEdited.emit()
        if dualSwathPolicyEdited:
            self.dualSwathPolicyEdited.emit()
