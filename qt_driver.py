###########################################################################
#
# Copyright 2015-2016 Robert B. Lowrie (http://github.com/lowrie)
#
# This file is part of pyRouterJig.
#
# pyRouterJig is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# pyRouterJig is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# pyRouterJig; see the file LICENSE. If not, see <http://www.gnu.org/licenses/>.
#
###########################################################################

'''
Contains the main driver, using pySide or pyQt.
'''
from __future__ import print_function
from future.utils import lrange
from builtins import str

import os, sys, traceback, webbrowser, copy

import qt_fig
import config_file
import router
import spacing
import utils
import doc
import serialize

from PyQt4 import QtCore, QtGui
#from PySide import QtCore, QtGui

class MyComboBox(QtGui.QComboBox):
    '''
    This comboxbox emits "activated" when hidePopup is called.  This allows
    for a combobox with a preview mode, so that as each selection is
    highlighted with the popup open, the figure can be updated.  Once the
    popup is closed, this hidePopup ensures that the figure is redrawn with
    the current actual selection.

    '''
    def __init__(self, parent):
        QtGui.QComboBox.__init__(self, parent)

    def hidePopup(self):
        QtGui.QComboBox.hidePopup(self)
        #print('hidePopup')
        self.activated.emit(self.currentIndex())

def set_line_style(line):
    '''Sets the style for create_vline() and create_hline()'''
    line.setFrameShadow(QtGui.QFrame.Raised)
    line.setLineWidth(1)
    line.setMidLineWidth(1)
    line.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)

def create_vline():
    '''Creates a vertical line'''
    vline = QtGui.QFrame()
    vline.setFrameStyle(QtGui.QFrame.VLine)
    set_line_style(vline)
    return vline

def create_hline():
    '''Creates a horizontal line'''
    hline = QtGui.QFrame()
    hline.setFrameStyle(QtGui.QFrame.HLine)
    set_line_style(hline)
    return hline

class Driver(QtGui.QMainWindow):
    '''
    Qt driver for pyRouterJig
    '''
    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        sys.excepthook = self.exception_hook
        self.except_handled = False

        # Read the config file.  We wait until the end of this init to print
        # the status message, because we need the statusbar to be created first.
        (self.config, msg, msg_level) = config_file.read_config(70)

        # Ensure config file is up-to-date
        if msg_level > 0:
            QtGui.QMessageBox.warning(self, 'Warning', msg)
            msg = ''

        # Default is English units, 1/32" resolution
        self.units = utils.Units(self.config.increments_per_inch, self.config.metric)
        self.doc = doc.Doc(self.units)

        # Create an initial joint.  Even though another joint may be opened
        # later, we do this now so that the initial widget layout may be
        # created.
        self.bit = router.Router_Bit(self.units, self.config.bit_width,\
                                     self.config.bit_depth, self.config.bit_angle)
        self.m_thickness = [4, 4] # initial thickness of M0 and M1 boards
        self.boards = []
        for i in lrange(4):
            self.boards.append(router.Board(self.bit, width=self.config.board_width))
        self.boards[2].set_active(False)
        self.boards[3].set_active(False)
        self.boards[2].set_height(self.bit, self.m_thickness[0])
        self.boards[3].set_height(self.bit, self.m_thickness[1])
        self.do_caul = False # if true, do caul template
        self.template = router.Incra_Template(self.units, self.boards, self.do_caul)
        self.equal_spacing = spacing.Equally_Spaced(self.bit, self.boards, self.config)
        self.equal_spacing.set_cuts()
        self.var_spacing = spacing.Variable_Spaced(self.bit, self.boards, self.config)
        self.var_spacing.set_cuts()
        self.edit_spacing = spacing.Edit_Spaced(self.bit, self.boards, self.config)
        self.edit_spacing.set_cuts(self.equal_spacing.cuts)
        self.spacing = self.equal_spacing # the default
        self.spacing_index = None # to be set in layout_widgets()

        # Create the main frame and menus
        self.create_menu()
        self.create_status_bar()
        self.create_widgets()

        # Draw the initial figure
        self.draw()

        # Keep track whether the current figure has been saved.  We initialize to true,
        # because we assume that that the user does not want the default joint saved.
        self.file_saved = True

        # The working_dir is where we save files.  We start with the user home
        # directory.  Ideally, if using the script to start the program, then
        # we'd use the cwd, but that's complicated.
        self.working_dir = os.path.expanduser('~')

        # We form the screenshot and save filename from this index
        self.screenshot_index = None

        # Initialize keyboard modifiers
        self.control_key = False
        self.shift_key = False
        self.alt_key = False

        # ... show the status message from reading the configuration file
        self.statusbar.showMessage(msg)

    def center(self):
        '''Centers the app in the screen'''
        frameGm = self.frameGeometry()
        screen = QtGui.QApplication.desktop().screenNumber(QtGui.QApplication.desktop().cursor().pos())
        centerPoint = QtGui.QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())

    def exception_hook(self, etype, value, trace):
        '''
        Handler for all exceptions.
        '''
        if self.except_handled:
            return

        self.except_handled = True
        if self.config.debug:
            tmp = traceback.format_exception(etype, value, trace)
        else:
            tmp = traceback.format_exception_only(etype, value)
        exception = '\n'.join(tmp)

        QtGui.QMessageBox.warning(self, 'Error', exception)
        self.except_handled = False

    def create_menu(self):
        '''
        Creates the drop-down menus.
        '''
        self.menubar = self.menuBar()

        # always attach the menubar to the application window, even on the Mac
        self.menubar.setNativeMenuBar(False)

        # Add the file menu

        file_menu = self.menubar.addMenu('File')

        open_action = QtGui.QAction('&Open File...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.setStatusTip('Opens a previously saved image of joint')
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QtGui.QAction('&Save File...', self)
        save_action.setShortcut('Ctrl+S')
        save_action.setStatusTip('Saves an image of the joint to a file')
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        screenshot_action = QtGui.QAction('Screenshot...', self)
        screenshot_action.setShortcut('Ctrl+W')
        screenshot_action.setStatusTip('Saves an image of the pyRouterJig window to a file')
        screenshot_action.triggered.connect(self._on_screenshot)
        file_menu.addAction(screenshot_action)

        print_action = QtGui.QAction('&Print', self)
        print_action.setShortcut('Ctrl+P')
        print_action.setStatusTip('Print the figure')
        print_action.triggered.connect(self._on_print)
        file_menu.addAction(print_action)

        exit_action = QtGui.QAction('&Quit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.setStatusTip('Exit pyRouterJig')
        exit_action.triggered.connect(self._on_exit)
        file_menu.addAction(exit_action)

        # Add units menu

        units_menu = self.menubar.addMenu('Units')
        ag = QtGui.QActionGroup(self, exclusive=True)
        english_action = QtGui.QAction('English', self, checkable=True)
        units_menu.addAction(ag.addAction(english_action))
        self.metric_action = QtGui.QAction('Metric', self, checkable=True)
        units_menu.addAction(ag.addAction(self.metric_action))
        english_action.setChecked(True)
        english_action.triggered.connect(self._on_units)
        self.metric_action.triggered.connect(self._on_units)

        # Add view menu

        view_menu = self.menubar.addMenu('View')
        fullscreen_action = QtGui.QAction('&Fullscreen', self, checkable=True)
        fullscreen_action.setShortcut('Ctrl+F')
        fullscreen_action.setStatusTip('Toggle full-screen mode')
        fullscreen_action.triggered.connect(self._on_fullscreen)
        view_menu.addAction(fullscreen_action)
        caul_action = QtGui.QAction('Caul Template', self, checkable=True)
        caul_action.setStatusTip('Toggle caul template')
        caul_action.triggered.connect(self._on_caul)
        view_menu.addAction(caul_action)

        # Add the help menu

        help_menu = self.menubar.addMenu('Help')

        about_action = QtGui.QAction('&About', self)
        about_action.setShortcut('Ctrl+A')
        about_action.setStatusTip('About this program')
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

        doclink_action = QtGui.QAction('&Documentation', self)
        doclink_action.setStatusTip('Opens documentation page in web browser')
        doclink_action.triggered.connect(self._on_doclink)
        help_menu.addAction(doclink_action)

    def create_wood_combo_box(self, woods, patterns, has_none=False):
        '''
        Creates a wood selection combox box
        '''
#        cb = QtGui.QComboBox(self)
        cb = MyComboBox(self)
        # Set the default wood.
        if has_none:
            # If adding NONE, make that the default
            cb.addItem('NONE')
            defwood = 'NONE'
        else:
            defwood = 'DiagCrossPattern'
            if self.config.default_wood in self.woods.keys():
                defwood = self.config.default_wood
        # Add the woods in the wood_images directory
        skeys = sorted(woods.keys())
        for k in skeys:
            cb.addItem(k)
        # Next add patterns
        cb.insertSeparator(len(skeys))
        skeys = sorted(patterns.keys())
        for k in skeys:
            cb.addItem(k)
        # Set the index to the default wood
        i = cb.findText(defwood)
        cb.setCurrentIndex(i)
        # Don't let the user change the text for each selection
        cb.setEditable(False)
        return cb

    def create_widgets(self):
        '''
        Creates all of the widgets in the main panel
        '''
        self.main_frame = QtGui.QWidget()

        lineEditWidth = 80

        # Create the figure canvas, using mpl interface
        self.fig = qt_fig.Qt_Fig(self.template, self.boards, self.config)
        self.fig.canvas.setParent(self.main_frame)
        self.fig.canvas.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.fig.canvas.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
        self.fig.canvas.setFocus()

        # Board width line edit
        self.le_board_width_label = QtGui.QLabel('Board Width')
        self.le_board_width = QtGui.QLineEdit(self.main_frame)
        self.le_board_width.setFixedWidth(lineEditWidth)
        self.le_board_width.setText(self.units.increments_to_string(self.boards[0].width))
        self.le_board_width.editingFinished.connect(self._on_board_width)
        self.le_board_width.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Fixed)

        # Bit width line edit
        self.le_bit_width_label = QtGui.QLabel('Bit Width')
        self.le_bit_width = QtGui.QLineEdit(self.main_frame)
        self.le_bit_width.setFixedWidth(lineEditWidth)
        self.le_bit_width.setText(self.units.increments_to_string(self.bit.width))
        self.le_bit_width.editingFinished.connect(self._on_bit_width)

        # Bit depth line edit
        self.le_bit_depth_label = QtGui.QLabel('Bit Depth')
        self.le_bit_depth = QtGui.QLineEdit(self.main_frame)
        self.le_bit_depth.setFixedWidth(lineEditWidth)
        self.le_bit_depth.setText(self.units.increments_to_string(self.bit.depth))
        self.le_bit_depth.editingFinished.connect(self._on_bit_depth)

        # Bit angle line edit
        self.le_bit_angle_label = QtGui.QLabel('Bit Angle')
        self.le_bit_angle = QtGui.QLineEdit(self.main_frame)
        self.le_bit_angle.setFixedWidth(lineEditWidth)
        self.le_bit_angle.setText('%g' % self.bit.angle)
        self.le_bit_angle.editingFinished.connect(self._on_bit_angle)

        # Board M thicknesses
        self.le_boardm_label = []
        self.le_boardm = []
        for i in lrange(2):
            self.le_boardm_label.append(QtGui.QLabel('Thickness'))
            self.le_boardm.append(QtGui.QLineEdit(self.main_frame))
            self.le_boardm[i].setFixedWidth(lineEditWidth)
            self.le_boardm[i].setText(self.units.increments_to_string(self.m_thickness[i]))
        self.le_boardm[0].editingFinished.connect(self._on_boardm0)
        self.le_boardm[1].editingFinished.connect(self._on_boardm1)

        # Wood combo boxes
        woods = utils.create_wood_dict(self.config.wood_images)
        patterns = {'DiagCrossPattern':QtCore.Qt.DiagCrossPattern,\
                    'BDiagPattern':QtCore.Qt.BDiagPattern,\
                    'FDiagPattern':QtCore.Qt.FDiagPattern,\
                    'Dense1Pattern':QtCore.Qt.Dense1Pattern,\
                    'Dense5Pattern':QtCore.Qt.Dense5Pattern}
        # ... combine the wood images and patterns
        self.woods = copy.deepcopy(woods)
        self.woods.update(patterns)
        # ... create the combo boxes and their labels
        self.cb_wood = []
        self.cb_wood.append(self.create_wood_combo_box(woods, patterns))
        self.cb_wood.append(self.create_wood_combo_box(woods, patterns))
        self.cb_wood.append(self.create_wood_combo_box(woods, patterns, True))
        self.cb_wood.append(self.create_wood_combo_box(woods, patterns, True))
        self.cb_wood_label = []
        self.cb_wood_label.append(QtGui.QLabel('Top Board'))
        self.cb_wood_label.append(QtGui.QLabel('Bottom Board'))
        self.cb_wood_label.append(QtGui.QLabel('Double Board'))
        self.cb_wood_label.append(QtGui.QLabel('Double-Double Board'))

        # Disable double* boards, for now
        self.le_boardm[0].setEnabled(False)
        self.le_boardm[1].setEnabled(False)
        self.le_boardm[0].setStyleSheet("color: gray;")
        self.le_boardm[1].setStyleSheet("color: gray;")
        self.le_boardm_label[0].setStyleSheet("color: gray;")
        self.le_boardm_label[1].setStyleSheet("color: gray;")
        self.cb_wood[3].setEnabled(False)
        self.cb_wood_label[3].setStyleSheet("color: gray;")

        # Equal spacing widgets

        params = self.equal_spacing.params
        labels = self.equal_spacing.labels

        # ...first slider
        p = params['Spacing']
        self.es_slider0_label = QtGui.QLabel(labels[0])
        self.es_slider0 = QtGui.QSlider(QtCore.Qt.Horizontal, self.main_frame)
        self.es_slider0.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.es_slider0.setMinimum(p.vMin)
        self.es_slider0.setMaximum(p.vMax)
        self.es_slider0.setValue(p.v)
        self.es_slider0.setTickPosition(QtGui.QSlider.TicksBelow)
        if p.vMax - p.vMin < 10:
            self.es_slider0.setTickInterval(1)
        self.es_slider0.valueChanged.connect(self._on_es_slider0)
        self.es_slider0.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)

        # ...second slider
        p = params['Width']
        self.es_slider1_label = QtGui.QLabel(labels[1])
        self.es_slider1 = QtGui.QSlider(QtCore.Qt.Horizontal, self.main_frame)
        self.es_slider1.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.es_slider1.setMinimum(p.vMin)
        self.es_slider1.setMaximum(p.vMax)
        self.es_slider1.setValue(p.v)
        self.es_slider1.setTickPosition(QtGui.QSlider.TicksBelow)
        if p.vMax - p.vMin < 10:
            self.es_slider1.setTickInterval(1)
        self.es_slider1.valueChanged.connect(self._on_es_slider1)
        self.es_slider1.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)

        # ...check box for centering
        p = params['Centered']
        self.cb_es_centered = QtGui.QCheckBox(labels[2], self.main_frame)
        self.cb_es_centered.setChecked(True)
        self.cb_es_centered.stateChanged.connect(self._on_cb_es_centered)

        # Variable spacing widgets

        params = self.var_spacing.params
        labels = self.var_spacing.labels

        # ...combox box for fingers
        p = params['Fingers']
        self.cb_vsfingers_label = QtGui.QLabel(labels[0])
        self.cb_vsfingers = MyComboBox(self.main_frame)
        self.cb_vsfingers.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.update_cb_vsfingers(p.vMin, p.vMax, p.v)

        # Edit spacing widgets

        edit_btn_undo = QtGui.QPushButton('Undo', self.main_frame)
        edit_btn_undo.clicked.connect(self._on_edit_undo)
        edit_btn_undo.setToolTip('Undo the last change')
        edit_btn_add = QtGui.QPushButton('Add', self.main_frame)
        edit_btn_add.clicked.connect(self._on_edit_add)
        edit_btn_add.setToolTip('Add a cut (if there is space to add cuts)')
        edit_btn_del = QtGui.QPushButton('Delete', self.main_frame)
        edit_btn_del.clicked.connect(self._on_edit_del)
        edit_btn_del.setToolTip('Delete the active cuts')

        edit_move_label = QtGui.QLabel('Move')
        edit_move_label.setToolTip('Moves the active cuts')
        edit_btn_moveL = QtGui.QToolButton(self.main_frame)
        edit_btn_moveL.setArrowType(QtCore.Qt.LeftArrow)
        edit_btn_moveL.clicked.connect(self._on_edit_moveL)
        edit_btn_moveL.setToolTip('Move active cuts to left 1 increment')
        edit_btn_moveR = QtGui.QToolButton(self.main_frame)
        edit_btn_moveR.setArrowType(QtCore.Qt.RightArrow)
        edit_btn_moveR.clicked.connect(self._on_edit_moveR)
        edit_btn_moveR.setToolTip('Move active cuts to right 1 increment')

        edit_widen_label = QtGui.QLabel('Widen')
        edit_widen_label.setToolTip('Widens the active cuts')
        edit_btn_widenL = QtGui.QToolButton(self.main_frame)
        edit_btn_widenL.setArrowType(QtCore.Qt.LeftArrow)
        edit_btn_widenL.clicked.connect(self._on_edit_widenL)
        edit_btn_widenL.setToolTip('Widen active cuts 1 increment on left side')
        edit_btn_widenR = QtGui.QToolButton(self.main_frame)
        edit_btn_widenR.setArrowType(QtCore.Qt.RightArrow)
        edit_btn_widenR.clicked.connect(self._on_edit_widenR)
        edit_btn_widenR.setToolTip('Widen active cuts 1 increment on right side')

        edit_trim_label = QtGui.QLabel('Trim')
        edit_trim_label.setToolTip('Trims the active cuts')
        edit_btn_trimL = QtGui.QToolButton(self.main_frame)
        edit_btn_trimL.setArrowType(QtCore.Qt.LeftArrow)
        edit_btn_trimL.clicked.connect(self._on_edit_trimL)
        edit_btn_trimL.setToolTip('Trim active cuts 1 increment on left side')
        edit_btn_trimR = QtGui.QToolButton(self.main_frame)
        edit_btn_trimR.setArrowType(QtCore.Qt.RightArrow)
        edit_btn_trimR.clicked.connect(self._on_edit_trimR)
        edit_btn_trimR.setToolTip('Trim active cuts 1 increment on right side')

        edit_btn_toggle = QtGui.QPushButton('Toggle', self.main_frame)
        edit_btn_toggle.clicked.connect(self._on_edit_toggle)
        edit_btn_toggle.setToolTip('Toggles the cut at cursor between active and deactive')
        edit_btn_cursorL = QtGui.QToolButton(self.main_frame)
        edit_btn_cursorL.setArrowType(QtCore.Qt.LeftArrow)
        edit_btn_cursorL.clicked.connect(self._on_edit_cursorL)
        edit_btn_cursorL.setToolTip('Move cut cursor to left')
        edit_btn_cursorR = QtGui.QToolButton(self.main_frame)
        edit_btn_cursorR.setArrowType(QtCore.Qt.RightArrow)
        edit_btn_cursorR.clicked.connect(self._on_edit_cursorR)
        edit_btn_cursorR.setToolTip('Move cut cursor to right')
        edit_btn_activate_all = QtGui.QPushButton('All', self.main_frame)
        edit_btn_activate_all.clicked.connect(self._on_edit_activate_all)
        edit_btn_activate_all.setToolTip('Set all cuts to be active')
        edit_btn_deactivate_all = QtGui.QPushButton('None', self.main_frame)
        edit_btn_deactivate_all.clicked.connect(self._on_edit_deactivate_all)
        edit_btn_deactivate_all.setToolTip('Set no cuts to be active')

        ######################################################################
        # Layout widgets in the main frame
        ######################################################################

        # vbox contains all of the widgets in the main frame, positioned
        # vertically
        vbox = QtGui.QVBoxLayout()

        # Add the figure canvas to the top
        vbox.addWidget(self.fig.canvas)

        # hbox contains all of the control widgets
        # (everything but the canvas)
        hbox = QtGui.QHBoxLayout()

        # this grid contains all the lower-left input stuff
        grid = QtGui.QGridLayout()

        grid.addWidget(create_hline(), 0, 0, 2, 9, QtCore.Qt.AlignTop)
        grid.addWidget(create_vline(), 0, 0, 9, 1)

        # Add the board width label, board width input line edit,
        # all stacked vertically on the left side.
        grid.addWidget(self.le_board_width_label, 1, 1)
        grid.addWidget(self.le_board_width, 2, 1)
        grid.addWidget(create_vline(), 0, 2, 9, 1)

        # Add the bit width label and its line edit
        grid.addWidget(self.le_bit_width_label, 1, 3)
        grid.addWidget(self.le_bit_width, 2, 3)
        grid.addWidget(create_vline(), 0, 4, 9, 1)

        # Add the bit depth label and its line edit
        grid.addWidget(self.le_bit_depth_label, 1, 5)
        grid.addWidget(self.le_bit_depth, 2, 5)
        grid.addWidget(create_vline(), 0, 6, 9, 1)

        # Add the bit angle label and its line edit
        grid.addWidget(self.le_bit_angle_label, 1, 7)
        grid.addWidget(self.le_bit_angle, 2, 7)
        grid.addWidget(create_vline(), 0, 8, 9, 1)

        grid.addWidget(create_hline(), 3, 0, 2, 9, QtCore.Qt.AlignTop)

        grid.setRowStretch(2, 10)

        # Add the wood combo boxes
        grid.addWidget(self.cb_wood_label[0], 4, 1)
        grid.addWidget(self.cb_wood_label[1], 4, 3)
        grid.addWidget(self.cb_wood_label[2], 4, 5)
        grid.addWidget(self.cb_wood_label[3], 4, 7)
        grid.addWidget(self.cb_wood[0], 5, 1)
        grid.addWidget(self.cb_wood[1], 5, 3)
        grid.addWidget(self.cb_wood[2], 5, 5)
        grid.addWidget(self.cb_wood[3], 5, 7)

        # Add double* thickness line edits
        grid.addWidget(self.le_boardm_label[0], 6, 5)
        grid.addWidget(self.le_boardm_label[1], 6, 7)
        grid.addWidget(self.le_boardm[0], 7, 5)
        grid.addWidget(self.le_boardm[1], 7, 7)

        grid.addWidget(create_hline(), 8, 0, 2, 9, QtCore.Qt.AlignTop)

        hbox.addLayout(grid)

        # Create the layout of the Equal spacing controls
        hbox_es = QtGui.QHBoxLayout()

        vbox_es_slider0 = QtGui.QVBoxLayout()
        vbox_es_slider0.addWidget(self.es_slider0_label)
        vbox_es_slider0.addWidget(self.es_slider0)
        hbox_es.addLayout(vbox_es_slider0)

        vbox_es_slider1 = QtGui.QVBoxLayout()
        vbox_es_slider1.addWidget(self.es_slider1_label)
        vbox_es_slider1.addWidget(self.es_slider1)
        hbox_es.addLayout(vbox_es_slider1)

        hbox_es.addWidget(self.cb_es_centered)

        # Create the layout of the Variable spacing controls.  Given only one
        # item, this is overkill, but the coding allows us to add additional
        # controls later.
        hbox_vs = QtGui.QHBoxLayout()
        hbox_vs.addWidget(self.cb_vsfingers_label)
        hbox_vs.addWidget(self.cb_vsfingers)
        hbox_vs.addStretch(1)

        # Create the layout of the edit spacing controls
        hbox_edit = QtGui.QHBoxLayout()
        grid_edit = QtGui.QGridLayout()
        grid_edit.addWidget(create_hline(), 0, 0, 2, 16, QtCore.Qt.AlignTop)
        grid_edit.addWidget(create_hline(), 2, 0, 2, 16, QtCore.Qt.AlignTop)
        grid_edit.addWidget(create_vline(), 0, 0, 6, 1)
        label_active_cut_select = QtGui.QLabel('Active Cut Select')
        label_active_cut_select.setToolTip('Tools that select the active cuts')
        grid_edit.addWidget(label_active_cut_select, 1, 1, 1, 3, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_btn_toggle, 3, 1, 1, 2, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_btn_cursorL, 4, 1, QtCore.Qt.AlignRight)
        grid_edit.addWidget(edit_btn_cursorR, 4, 2, QtCore.Qt.AlignLeft)
        grid_edit.addWidget(edit_btn_activate_all, 3, 3)
        grid_edit.addWidget(edit_btn_deactivate_all, 4, 3)
        grid_edit.addWidget(create_vline(), 0, 4, 6, 1)
        label_active_cut_ops = QtGui.QLabel('Active Cut Operators')
        label_active_cut_ops.setToolTip('Edit operations applied to active cuts')
        grid_edit.addWidget(label_active_cut_ops, 1, 5, 1, 10, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_move_label, 3, 5, 1, 2, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_btn_moveL, 4, 5, QtCore.Qt.AlignRight)
        grid_edit.addWidget(edit_btn_moveR, 4, 6, QtCore.Qt.AlignLeft)
        grid_edit.addWidget(create_vline(), 2, 7, 4, 1)
        grid_edit.addWidget(edit_widen_label, 3, 8, 1, 2, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_btn_widenL, 4, 8, QtCore.Qt.AlignRight)
        grid_edit.addWidget(edit_btn_widenR, 4, 9, QtCore.Qt.AlignLeft)
        grid_edit.addWidget(create_vline(), 2, 10, 4, 1)
        grid_edit.addWidget(edit_trim_label, 3, 11, 1, 2, QtCore.Qt.AlignHCenter)
        grid_edit.addWidget(edit_btn_trimL, 4, 11, QtCore.Qt.AlignRight)
        grid_edit.addWidget(edit_btn_trimR, 4, 12, QtCore.Qt.AlignLeft)
        grid_edit.addWidget(create_vline(), 2, 13, 4, 1)
        grid_edit.addWidget(edit_btn_add, 3, 14)
        grid_edit.addWidget(edit_btn_del, 4, 14)
        grid_edit.addWidget(create_vline(), 0, 15, 6, 1)
        grid_edit.addWidget(create_hline(), 5, 0, 2, 16, QtCore.Qt.AlignTop)
        grid_edit.setSpacing(5)

        hbox_edit.addLayout(grid_edit)
        hbox_edit.addStretch(1)
        hbox_edit.addWidget(edit_btn_undo)

        # Add the spacing layouts as Tabs
        self.tabs_spacing = QtGui.QTabWidget()
        tab_es = QtGui.QWidget()
        tab_es.setLayout(hbox_es)
        self.tabs_spacing.addTab(tab_es, 'Equal')
        tab_vs = QtGui.QWidget()
        tab_vs.setLayout(hbox_vs)
        self.tabs_spacing.addTab(tab_vs, 'Variable')
        tab_edit = QtGui.QWidget()
        tab_edit.setLayout(hbox_edit)
        self.tabs_spacing.addTab(tab_edit, 'Editor')
        self.tabs_spacing.currentChanged.connect(self._on_tabs_spacing)
        tip = 'These tabs specify the layout algorithm for the cuts.'
        self.tabs_spacing.setToolTip(tip)

        # The tab indices should be set in the order they're defined, but this ensures it
        self.equal_spacing_id = self.tabs_spacing.indexOf(tab_es)
        self.var_spacing_id = self.tabs_spacing.indexOf(tab_vs)
        self.edit_spacing_id = self.tabs_spacing.indexOf(tab_edit)
        # set default spacing tab to Equal
        self.spacing_index = self.equal_spacing_id
        self.tabs_spacing.setCurrentIndex(self.spacing_index)

        # either add the spacing Tabs to the right of the line edits
        vbox_tabs = QtGui.QVBoxLayout()
        vbox_tabs.addWidget(self.tabs_spacing)
        vbox_tabs.addStretch(1)
        hbox.addStretch(1)
        hbox.addLayout(vbox_tabs)
        vbox.addLayout(hbox)

        # Lay it all out
        self.main_frame.setLayout(vbox)
        self.setCentralWidget(self.main_frame)

        # Finalize some settings
        self.cb_vsfingers.activated.connect(self._on_cb_vsfingers)
        self.cb_vsfingers.highlighted.connect(self._on_cb_vsfingers)
        self.cb_wood[0].activated.connect(self._on_wood0)
        self.cb_wood[1].activated.connect(self._on_wood1)
        self.cb_wood[2].activated.connect(self._on_wood2)
        self.cb_wood[3].activated.connect(self._on_wood3)
        self.cb_wood[0].highlighted.connect(self._on_wood0)
        self.cb_wood[1].highlighted.connect(self._on_wood1)
        self.cb_wood[2].highlighted.connect(self._on_wood2)
        self.cb_wood[3].highlighted.connect(self._on_wood3)
        self._on_wood(0)
        self._on_wood(1)
        self._on_wood(2)
        self._on_wood(3)
        self.update_tooltips()

    def update_cb_vsfingers(self, vMin, vMax, value):
        '''
        Updates the combobox for Variable spacing Fingers.
        '''
        self.cb_vsfingers.clear()
        for i in lrange(vMin, vMax + 1, 1):
            self.cb_vsfingers.addItem(`i`)
        i = self.cb_vsfingers.findText(`value`)
        self.cb_vsfingers.setCurrentIndex(i)

    def update_tooltips(self):
        '''
        [Re]sets the tool tips for widgets whose tips depend on user settings
        '''

        disable = ''
        if self.spacing_index == self.edit_spacing_id:
            disable = '  <b>Cannot change if in Editor mode.</b>'

        disable_double = disable
        if not self.boards[2].active:
            disable_double = '  <b>Cannot change unless "Double Board" is not NONE.</b>'
        disable_dd = disable
        if not self.boards[3].active:
            disable_dd = '  <b>Cannot change unless "Double-Double Board" is not NONE.</b>'

        self.le_board_width_label.setToolTip(self.doc.board_width() + disable)
        self.le_board_width.setToolTip(self.doc.board_width() + disable)
        self.le_bit_width_label.setToolTip(self.doc.bit_width() + disable)
        self.le_bit_width.setToolTip(self.doc.bit_width() + disable)
        self.le_bit_depth_label.setToolTip(self.doc.bit_depth() + disable)
        self.le_bit_depth.setToolTip(self.doc.bit_depth() + disable)
        self.le_bit_angle_label.setToolTip(self.doc.bit_angle() + disable)
        self.le_bit_angle.setToolTip(self.doc.bit_angle() + disable)

        self.cb_wood_label[0].setToolTip(self.doc.top_board() + disable)
        self.cb_wood[0].setToolTip(self.doc.top_board() + disable)
        self.cb_wood_label[1].setToolTip(self.doc.bottom_board() + disable)
        self.cb_wood[1].setToolTip(self.doc.bottom_board() + disable)
        self.cb_wood_label[2].setToolTip(self.doc.double_board() + disable)
        self.cb_wood[2].setToolTip(self.doc.double_board() + disable)
        self.cb_wood_label[3].setToolTip(self.doc.dd_board() + disable_double)
        self.cb_wood[3].setToolTip(self.doc.dd_board() + disable_double)

        self.le_boardm_label[0].setToolTip(self.doc.double_thickness() + disable_double)
        self.le_boardm[0].setToolTip(self.doc.double_thickness() + disable_double)
        self.le_boardm_label[1].setToolTip(self.doc.dd_thickness() + disable_dd)
        self.le_boardm[1].setToolTip(self.doc.dd_thickness() + disable_dd)

        self.es_slider0_label.setToolTip(self.doc.es_slider0())
        self.es_slider0.setToolTip(self.doc.es_slider0())
        self.es_slider1_label.setToolTip(self.doc.es_slider1())
        self.es_slider1.setToolTip(self.doc.es_slider1())
        self.cb_es_centered.setToolTip(self.doc.es_centered())
        self.cb_vsfingers_label.setToolTip(self.doc.cb_vsfingers())
        self.cb_vsfingers.setToolTip(self.doc.cb_vsfingers())

    def create_status_bar(self):
        '''
        Creates a status message bar that is placed at the bottom of the
        main frame.
        '''
        self.statusbar = self.statusBar()
        self.statusbar.showMessage('Ready')

    def draw(self):
        '''(Re)draws the template and boards'''
        if self.config.debug:
            print('draw')
        self.template = router.Incra_Template(self.units, self.boards, self.do_caul)
        self.fig.draw(self.template, self.boards, self.bit, self.spacing, self.woods)

    def reinit_spacing(self):
        '''
        Re-initializes the joint spacing objects.  This must be called
        when the router bit or board change dimensions.
        '''
        self.spacing_index = self.tabs_spacing.currentIndex()

        # Re-create the spacings objects
        if self.spacing_index == self.equal_spacing_id:
            self.equal_spacing = spacing.Equally_Spaced(self.bit, self.boards, self.config)
        elif self.spacing_index == self.var_spacing_id:
            self.var_spacing = spacing.Variable_Spaced(self.bit, self.boards, self.config)
        elif self.spacing_index == self.edit_spacing_id:
            self.edit_spacing = spacing.Edit_Spaced(self.bit, self.boards, self.config)
        else:
            raise ValueError('Bad value for spacing_index %d' % self.spacing_index)

        self.set_spacing_widgets()

    def set_spacing_widgets(self):
        '''
        Sets the spacing widget parameters
        '''
        # enable/disable changing parameters, depending upon spacing algorithm
        les = [self.le_board_width, self.le_board_width_label,\
               self.le_bit_width, self.le_bit_width_label,\
               self.le_bit_depth, self.le_bit_depth_label,\
               self.le_bit_angle, self.le_bit_angle_label]
        les.extend(self.cb_wood)
        les.extend(self.cb_wood_label)
        les.extend(self.le_boardm)
        les.extend(self.le_boardm_label)
        if self.spacing_index == self.edit_spacing_id:
            for le in les:
                le.blockSignals(True)
                le.setEnabled(False)
                le.setStyleSheet("color: gray;")
                le.blockSignals(False)
        else:
            for le in les:
                le.blockSignals(True)
                le.setEnabled(True)
                le.setStyleSheet("color: black;")
                le.blockSignals(False)
            if not self.boards[2].active:
                disable = self.le_boardm
                disable.extend(self.le_boardm_label)
                disable.append(self.cb_wood[3])
                disable.append(self.cb_wood_label[3])
                for le in disable:
                    le.blockSignals(True)
                    le.setEnabled(False)
                    le.setStyleSheet("color: gray;")
                    le.blockSignals(False)
            if not self.boards[3].active:
                disable = [self.le_boardm[1], self.le_boardm_label[1]]
                for le in disable:
                    le.blockSignals(True)
                    le.setEnabled(False)
                    le.setStyleSheet("color: gray;")
                    le.blockSignals(False)

        # Set up the various widgets for each spacing option
        if self.spacing_index == self.equal_spacing_id:
            # Equal spacing widgets
            params = self.equal_spacing.params
            p = params['Spacing']
            self.es_slider0.blockSignals(True)
            self.es_slider0.setMinimum(p.vMin)
            self.es_slider0.setMaximum(p.vMax)
            self.es_slider0.setValue(p.v)
            self.es_slider0.blockSignals(False)
            p = params['Width']
            self.es_slider1.blockSignals(True)
            self.es_slider1.setMinimum(p.vMin)
            self.es_slider1.setMaximum(p.vMax)
            self.es_slider1.setValue(p.v)
            self.es_slider1.blockSignals(False)
            p = params['Centered']
            centered = p.v
            self.cb_es_centered.blockSignals(True)
            self.cb_es_centered.setChecked(centered)
            self.cb_es_centered.blockSignals(False)

            self.equal_spacing.set_cuts()
            self.es_slider0_label.setText(self.equal_spacing.labels[0])
            self.es_slider1_label.setText(self.equal_spacing.labels[1])
            self.spacing = self.equal_spacing
        elif self.spacing_index == self.var_spacing_id:
            # Variable spacing widgets
            params = self.var_spacing.params
            p = params['Fingers']
            self.cb_vsfingers.blockSignals(True)
            self.update_cb_vsfingers(p.vMin, p.vMax, p.v)
            self.cb_vsfingers.blockSignals(False)
            self.var_spacing.set_cuts()
            self.cb_vsfingers_label.setText(self.var_spacing.keys[0] + ':')
            self.spacing = self.var_spacing
        elif self.spacing_index == self.edit_spacing_id:
            # Edit spacing parameters.  Currently, this has no parameters, and
            # uses as a starting spacing whatever the previous spacing set.
            self.edit_spacing.set_cuts(self.spacing.cuts)
            self.spacing = self.edit_spacing
        else:
            raise ValueError('Bad value for spacing_index %d' % self.spacing_index)

        self.update_tooltips()

    @QtCore.pyqtSlot(int)
    def _on_tabs_spacing(self, index):
        '''Handles changes to spacing algorithm'''
        if self.config.debug:
            print('_on_tabs_spacing')
        if self.spacing_index == self.edit_spacing_id and index != self.edit_spacing_id and \
                    self.spacing.changes_made():
            msg = 'You are exiting the Editor, which will discard'\
                  ' any changes made in the Editor.'\
                  '\n\nAre you sure you want to do this?'
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.No:
                self.tabs_spacing.setCurrentIndex(self.spacing_index)
                return
        self.reinit_spacing()
        self.draw()
        self.status_message('Changed to spacing algorithm %s'\
                            % str(self.tabs_spacing.tabText(index)))
        self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_bit_width(self):
        '''Handles changes to bit width'''
        if self.config.debug:
            print('_on_bit_width')
        # With editingFinished, we also need to check whether the
        # value actually changed. This is because editingFinished gets
        # triggered every time focus changes, which can occur many
        # times when an exception is thrown, or user tries to quit
        # in the middle of an exception, etc.  This logic also avoids
        # unnecessary redraws.
        if self.le_bit_width.isModified():
            if self.config.debug:
                print(' bit_width modified')
            self.le_bit_width.setModified(False)
            text = str(self.le_bit_width.text())
            self.bit.set_width_from_string(text)
            self.reinit_spacing()
            self.draw()
            self.status_message('Changed bit width to ' + text)
            self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_bit_depth(self):
        '''Handles changes to bit depth'''
        if self.config.debug:
            print('_on_bit_depth')
        if self.le_bit_depth.isModified():
            self.le_bit_depth.setModified(False)
            text = str(self.le_bit_depth.text())
            self.bit.set_depth_from_string(text)
            for b in self.boards:
                b.set_height(self.bit)
            self.draw()
            self.status_message('Changed bit depth to ' + text)
            self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_bit_angle(self):
        '''Handles changes to bit angle'''
        if self.config.debug:
            print('_on_bit_angle')
        if self.le_bit_angle.isModified():
            self.le_bit_angle.setModified(False)
            text = str(self.le_bit_angle.text())
            self.bit.set_angle_from_string(text)
            self.reinit_spacing()
            self.draw()
            self.status_message('Changed bit angle to ' + text)
            self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_board_width(self):
        '''Handles changes to board width'''
        if self.config.debug:
            print('_on_board_width')
        if self.le_board_width.isModified():
            self.le_board_width.setModified(False)
            text = str(self.le_board_width.text())
            self.boards[0].set_width_from_string(text)
            for b in self.boards[1:]:
                b.width = self.boards[0].width
            self.reinit_spacing()
            self.draw()
            self.status_message('Changed board width to ' + text)
            self.file_saved = False

    @QtCore.pyqtSlot(int)
    def _on_es_slider0(self, value):
        '''Handles changes to the equally-spaced slider spacing'''
        if self.config.debug:
            print('_on_es_slider0', value)
        self.equal_spacing.params['Spacing'].v = value
        self.equal_spacing.set_cuts()
        self.es_slider0_label.setText(self.equal_spacing.labels[0])
        self.draw()
        self.status_message('Changed slider %s' % str(self.es_slider0_label.text()))
        self.file_saved = False

    @QtCore.pyqtSlot(int)
    def _on_es_slider1(self, value):
        '''Handles changes to the equally-spaced slider Width'''
        if self.config.debug:
            print('_on_es_slider1', value)
        self.equal_spacing.params['Width'].v = value
        self.equal_spacing.set_cuts()
        self.es_slider1_label.setText(self.equal_spacing.labels[1])
        self.draw()
        self.status_message('Changed slider %s' % str(self.es_slider1_label.text()))
        self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_cb_es_centered(self):
        '''Handles changes to centered checkbox'''
        if self.config.debug:
            print('_on_cb_es_centered')
        self.equal_spacing.params['Centered'].v = self.cb_es_centered.isChecked()
        self.equal_spacing.set_cuts()
        self.draw()
        if self.equal_spacing.params['Centered'].v:
            self.status_message('Checked Centered.')
        else:
            self.status_message('Unchecked Centered.')
        self.file_saved = False

    @QtCore.pyqtSlot(int)
    def _on_cb_vsfingers(self, index):
        '''Handles changes to the variable-spaced slider Fingers'''
        if self.config.debug:
            print('_on_cb_vsfingers', index)
        self.var_spacing.params['Fingers'].v = int(self.cb_vsfingers.itemText(index))
        self.var_spacing.set_cuts()
        self.cb_vsfingers_label.setText(self.var_spacing.keys[0] + ':')
        self.draw()
        self.status_message('Changed slider %s' % str(self.cb_vsfingers_label.text()))
        self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_screenshot(self):
        '''
        Handles screenshot events.
        '''
        if self.config.debug:
            print('_on_screenshot')
        self._on_save(True)

    @QtCore.pyqtSlot()
    def _on_save(self, do_screenshot=False):
        '''
        Handles save file events. The file format is PNG, with metadata
        to support recreating the joint.
        '''
        if self.config.debug:
            print('_on_save')

        prefix = 'pyrouterjig_'
        postfix = '.png'
        if self.screenshot_index is None:
            self.screenshot_index = utils.get_file_index(self.working_dir, prefix, postfix)

        fname = prefix + `self.screenshot_index` + postfix

        # Get the file name.  The default name is indexed on the number of
        # times this function is called.  If a screenshot, don't prompt for
        # the filename and use the default name
        defname = os.path.join(self.working_dir, fname)
        if do_screenshot:
            filename = defname
        else:
            # This is the simple approach to set the filename, but doesn't allow
            # us to update the working_dir, if the user changes it.
            #filename = QtGui.QFileDialog.getSaveFileName(self, 'Save file', \
            #                     defname, 'Portable Network Graphics (*.png)')
            # ... so here is now we do it:
            dialog = QtGui.QFileDialog(self, 'Save file', defname, \
                                       'Portable Network Graphics (*.png)')
            dialog.setFileMode(QtGui.QFileDialog.AnyFile)
            dialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
            filename = None
            if dialog.exec_():
                filenames = dialog.selectedFiles()
                d = str(dialog.directory().path())
                # force recomputation of index, next time around, if path changed
                if d != self.working_dir:
                    self.screenshot_index = None
                self.working_dir = d
                filename = str(filenames[0]).strip()
            if filename is None:
                self.status_message('File not saved')
                return

        # Save the file with metadata
        if do_screenshot:
            image = QtGui.QPixmap.grabWindow(self.winId()).toImage()
        else:
            image = self.fig.image(self.template, self.boards, self.bit, self.spacing, self.woods,\
                                   self.config.min_image_width)

        s = serialize.serialize(self.bit, self.boards, self.spacing, \
                                self.config)
        image.setText('pyRouterJig', s)
        r = image.save(filename, 'png')
        if r:
            self.status_message('Saved to file %s' % filename)
            if self.screenshot_index is not None:
                self.screenshot_index += 1
            self.file_saved = True
        else:
            self.status_message('Unable to save to file %s' % filename)

    @QtCore.pyqtSlot()
    def _on_open(self):
        '''
        Handles open file events.  The file format is  PNG, with metadata
        to support recreating the joint.  In other words, the file must
        have been saved using _on_save().
        '''
        if self.config.debug:
            print('_on_open')

        # Make sure changes are not lost
        if not self.file_saved:
            msg = 'Current joint not saved.'\
                  ' Opening a new file will overwrite the current joint.'\
                  '\n\nAre you sure you want to do this?'
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.No:
                return

        # Get the file name
        filename = QtGui.QFileDialog.getOpenFileName(self, 'Open file', \
                                                     self.working_dir, \
                                                     'Portable Network Graphics (*.png)')
        filename = str(filename).strip()
        if len(filename) == 0:
            self.status_message('File open aborted')
            return

        # From the image file, parse the metadata.
        image = QtGui.QImage(filename)
        s = image.text('pyRouterJig') # see setText in _on_save
        if len(s) == 0:
            msg = 'File %s does not contain pyRouterJig data.  The PNG file'\
                  ' must have been saved using pyRouterJig.' % filename
            QtGui.QMessageBox.warning(self, 'Error', msg)
            return
        (self.bit, self.boards, sp, sp_type) = serialize.unserialize(s, self.config)

        # Reset the dependent data
        self.units = self.bit.units
        self.template = router.Incra_Template(self.units, self.boards, self.do_caul)

        # ... set the wood selection for each board.  If the wood does not
        # exist, set to a wood we know exists.  This can happen if the wood
        # image files don't exist across users.
        for i in lrange(4):
            if self.boards[i].wood is None:
                self.boards[i].set_wood('NONE')
            elif self.boards[i].wood not in self.woods.keys():
                self.boards[i].set_wood('DiagCrossPattern')
            j = self.cb_wood[i].findText(self.boards[i].wood)
            self.cb_wood[i].setCurrentIndex(j)

        # ... set double* board input parameters.  The double* inputs are
        # activated/deactivated in set_spacing_parameters(), called below
        if self.boards[2].active:
            self.le_boardm[0].setText(self.units.increments_to_string(self.boards[2].dheight))
            if self.boards[3].active:
                self.le_boardm[1].setText(self.units.increments_to_string(self.boards[3].dheight))
        else:
            i = self.cb_wood[3].findText('NONE')
            self.cb_wood[3].setCurrentIndex(i)

        # ... set spacing cuts and tabs
        if sp_type == 'Equa':
            sp.set_cuts()
            self.equal_spacing = sp
            self.spacing_index = self.equal_spacing_id
        elif sp_type == 'Vari':
            sp.set_cuts()
            self.var_spacing = sp
            self.spacing_index = self.var_spacing_id
        elif sp_type == 'Edit':
            self.edit_spacing = sp
            self.spacing_index = self.edit_spacing_id

        self.spacing = sp
        self.tabs_spacing.blockSignals(True)
        self.tabs_spacing.setCurrentIndex(self.spacing_index)
        self.tabs_spacing.blockSignals(False)

        # ... set line edit parameters
        self.le_board_width.setText(self.units.increments_to_string(self.boards[0].width))
        self.le_bit_width.setText(self.units.increments_to_string(self.bit.width))
        self.le_bit_depth.setText(self.units.increments_to_string(self.bit.depth))
        self.le_bit_angle.setText(`self.bit.angle`)
        self.set_spacing_widgets()

        self.draw()

    @QtCore.pyqtSlot()
    def _on_print(self):
        '''Handles print events'''
        if self.config.debug:
            print('_on_print')

        r = self.fig.print(self.template, self.boards, self.bit, self.spacing, self.woods)
        if r:
            self.status_message('Figure printed')
        else:
            self.status_message('Figure not printed')

    @QtCore.pyqtSlot()
    def _on_exit(self):
        '''Handles code exit events'''
        if self.config.debug:
            print('_on_exit')
        if self.file_saved:
            QtGui.qApp.quit()
        else:
            msg = 'Figure was changed but not saved.  Are you sure you want to quit?'
            reply = QtGui.QMessageBox.question(self, 'Message', msg,
                                               QtGui.QMessageBox.Yes,
                                               QtGui.QMessageBox.No)

            if reply == QtGui.QMessageBox.Yes:
                QtGui.qApp.quit()

    @QtCore.pyqtSlot()
    def _on_about(self):
        '''Handles about dialog event'''
        if self.config.debug:
            print('_on_about')

        box = QtGui.QMessageBox(self)
        s = '<h2>Welcome to pyRouterJig!</h2>'
        s += '<h3>Version: %s</h3>' % utils.VERSION
        box.setText(s + self.doc.short_desc() + self.doc.license())
        box.setTextFormat(QtCore.Qt.RichText)
        box.show()

    @QtCore.pyqtSlot()
    def _on_doclink(self):
        '''Handles doclink event'''
        if self.config.debug:
            print('_on_doclink')

        webbrowser.open('http://lowrie.github.io/pyRouterJig/documentation.html')

    @QtCore.pyqtSlot()
    def _on_units(self):
        '''Handles changes in units'''
        if self.config.debug:
            print('_on_units')
        do_metric = self.metric_action.isChecked()
        if self.metric == do_metric:
            return # no change in units
        if do_metric:
            self.units = utils.Units(metric=True)
        else:
            self.units = utils.Units(32)
        for b in self.boards:
            b.change_units(self.units)
        self.bit.change_units(self.units)
        self.doc.change_units(self.units)
        self.le_board_width.setText(self.units.increments_to_string(self.boards[0].width))
        self.le_bit_width.setText(self.units.increments_to_string(self.bit.width))
        self.le_bit_depth.setText(self.units.increments_to_string(self.bit.depth))
        self.reinit_spacing()
        self.update_tooltips()
        self.draw()

    def _on_wood(self, iwood, index=None, reinit=False):
        '''Handles all changes in wood'''
        if self.config.debug:
            print('_on_wood', iwood, index)
        if index is None:
            index = self.cb_wood[iwood].currentIndex()
        s = str(self.cb_wood[iwood].itemText(index))
        label = str(self.cb_wood_label[iwood].text())
        if s != 'NONE':
            self.boards[iwood].set_wood(s)
        if reinit:
            self.reinit_spacing()
        self.draw()
        self.file_saved = False
        msg = 'Changed %s to %s' % (label, s)
        self.statusbar.showMessage(msg)

    @QtCore.pyqtSlot(int)
    def _on_wood0(self, index):
        '''Handles changes in wood index 0'''
        if self.config.debug:
            print('_on_wood0', index)
        self._on_wood(0, index)

    @QtCore.pyqtSlot(int)
    def _on_wood1(self, index):
        '''Handles changes in wood index 1'''
        if self.config.debug:
            print('_on_wood1', index)
        self._on_wood(1, index)

    @QtCore.pyqtSlot(int)
    def _on_wood2(self, index):
        '''Handles changes in wood index 2'''
        if self.config.debug:
            print('_on_wood2', index)
        s = str(self.cb_wood[2].itemText(index))
        reinit = False
        if s == 'NONE':
            if self.boards[2].active:
                reinit = True
            i = self.cb_wood[3].findText('NONE')
            self.cb_wood[3].setCurrentIndex(i)
            self.cb_wood[3].setEnabled(False)
            self.boards[2].set_active(False)
            self.boards[3].set_active(False)
            self.le_boardm[0].setEnabled(False)
            self.le_boardm[1].setEnabled(False)
            self.le_boardm[0].setStyleSheet("color: gray;")
            self.le_boardm[1].setStyleSheet("color: gray;")
        else:
            if not self.boards[2].active:
                reinit = True
            self.cb_wood[3].setEnabled(True)
            self.boards[2].set_active(True)
            self.le_boardm[0].setEnabled(True)
            self.le_boardm[0].setStyleSheet("color: black;")
        self._on_wood(2, index, reinit)

    @QtCore.pyqtSlot(int)
    def _on_wood3(self, index):
        '''Handles changes in wood index 3'''
        if self.config.debug:
            print('_on_wood3', index)
        s = str(self.cb_wood[3].itemText(index))
        reinit = False
        if s == 'NONE':
            if self.boards[3].active:
                reinit = True
            self.boards[3].set_active(False)
            self.le_boardm[1].setEnabled(False)
            self.le_boardm[1].setStyleSheet("color: gray;")
        else:
            if not self.boards[3].active:
                reinit = True
            self.boards[3].set_active(True)
            self.le_boardm[1].setEnabled(True)
            self.le_boardm[1].setStyleSheet("color: black;")
        self._on_wood(3, index, reinit)

    def _on_boardm(self, i):
        '''Handles changes board-M height changes'''
        if self.le_boardm[i].isModified():
            if self.config.debug:
                print('_on_boardm', i)
            self.le_boardm[i].setModified(False)
            text = str(self.le_boardm[i].text())
            self.boards[i + 2].set_height_from_string(self.bit, text)
            self.reinit_spacing()
            self.draw()
            labels = ['Double', 'Double-Double']
            self.status_message(('Changed %s Board thickness to ' + text) % labels[i])
            self.reinit_spacing()
            self.file_saved = False

    @QtCore.pyqtSlot()
    def _on_boardm0(self):
        '''Handles changes board-M0 height'''
        self._on_boardm(0)

    @QtCore.pyqtSlot()
    def _on_boardm1(self):
        '''Handles changes board-M1 height'''
        self._on_boardm(1)

    @QtCore.pyqtSlot()
    def _on_edit_undo(self):
        '''Handles undo event'''
        if self.config.debug:
            print('_on_edit_undo')
        self.spacing.undo()
        self.statusbar.showMessage('Undo')
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_moveL(self):
        '''Handles move left event'''
        if self.config.debug:
            print('_on_edit_moveL')
        msg = self.spacing.cut_move_left()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_moveR(self):
        '''Handles move right event'''
        if self.config.debug:
            print('_on_edit_moveR')
        msg = self.spacing.cut_move_right()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_widenL(self):
        '''Handles widen left event'''
        if self.config.debug:
            print('_on_edit_widenL')
        msg = self.spacing.cut_widen_left()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_widenR(self):
        '''Handles widen right event'''
        if self.config.debug:
            print('_on_edit_widenR')
        msg = self.spacing.cut_widen_right()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_trimL(self):
        '''Handles trim left event'''
        if self.config.debug:
            print('_on_edit_trimL')
        msg = self.spacing.cut_trim_left()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_trimR(self):
        '''Handles trim right event'''
        if self.config.debug:
            print('_on_edit_trimR')
        msg = self.spacing.cut_trim_right()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_toggle(self):
        '''Handles edit toggle event'''
        if self.config.debug:
            print('_on_edit_toggle')
        msg = self.spacing.cut_toggle()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_cursorL(self):
        '''Handles cursor left event'''
        if self.config.debug:
            print('_on_edit_cursorL')
        msg = self.spacing.cut_increment_cursor(-1)
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_cursorR(self):
        '''Handles toggle right event'''
        if self.config.debug:
            print('_on_edit_cursorR')
        msg = self.spacing.cut_increment_cursor(1)
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_activate_all(self):
        '''Handles edit activate all event'''
        if self.config.debug:
            print('_on_edit_activate_all')
        msg = self.spacing.cut_all_active()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_deactivate_all(self):
        '''Handles edit deactivate all event'''
        if self.config.debug:
            print('_on_edit_deactivate_all')
        msg = self.spacing.cut_all_not_active()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_add(self):
        '''Handles add cut event'''
        if self.config.debug:
            print('_on_edit_add')
        msg = self.spacing.cut_add()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_edit_del(self):
        '''Handles delete cuts event'''
        if self.config.debug:
            print('_on_edit_del')
        msg = self.spacing.cut_delete_active()
        self.statusbar.showMessage(msg)
        self.draw()

    @QtCore.pyqtSlot()
    def _on_flash_status_off(self):
        '''Handles event to turn off statusbar message'''
        if self.config.debug:
            print('_on_flash_status_off')
        self.statusbar.showMessage('')

    @QtCore.pyqtSlot()
    def _on_fullscreen(self):
        '''Handles toggling full-screen mode'''
        if self.config.debug:
            print('_on_fullscreen')
        if self.windowState() & QtCore.Qt.WindowFullScreen:
            self.showNormal()
            self.status_message('Exited full-screen mode.')
        else:
            self.showFullScreen()
            self.status_message('Entered full-screen mode.')

    @QtCore.pyqtSlot()
    def _on_caul(self):
        '''Handles toggling showing caul template'''
        if self.config.debug:
            print('_on_caul')
        if self.do_caul:
            self.do_caul = False
            self.status_message('Turned off caul template.')
        else:
            self.do_caul = True
            self.status_message('Turned on caul template.')
        self.file_saved = False
        self.draw()

    def status_message(self, msg, flash_len_ms=None):
        '''Flashes a status message to the status bar'''
        self.statusbar.showMessage(msg)
        if flash_len_ms is not None:
            QtCore.QTimer.singleShot(flash_len_ms, self._on_flash_status_off)

    def closeEvent(self, event):
        '''
        For closeEvents (user closes window or presses Ctrl-Q), ignore and call
        _on_exit()
        '''
        if self.config.debug:
            print('closeEvent')
        self._on_exit()
        event.ignore()

    def keyPressEvent(self, event):
        '''
        Handles key press events
        '''
        # return if not edit spacing
        if self.tabs_spacing.currentIndex() != self.edit_spacing_id:
            event.ignore()
            return

        msg = None
        if event.key() == QtCore.Qt.Key_Shift:
            self.shift_key = True
        elif event.key() == QtCore.Qt.Key_Control:
            self.control_key = True
        elif event.key() == QtCore.Qt.Key_Alt:
            self.alt_key = True
        elif event.key() == QtCore.Qt.Key_U:
            self.spacing.undo()
            msg = 'Undo'
            self.draw()
        elif event.key() == QtCore.Qt.Key_A:
            msg = self.spacing.cut_all_active()
            self.draw()
        elif event.key() == QtCore.Qt.Key_N:
            msg = self.spacing.cut_all_not_active()
            self.draw()
        elif event.key() == QtCore.Qt.Key_Return:
            msg = self.spacing.cut_toggle()
            self.draw()
        elif event.key() == QtCore.Qt.Key_Minus:
            msg = self.spacing.cut_delete_active()
            self.draw()
        elif event.key() == QtCore.Qt.Key_Plus:
            msg = self.spacing.cut_add()
            self.draw()
        elif event.key() == QtCore.Qt.Key_Left:
            if self.shift_key:
                msg = self.spacing.cut_widen_left()
            elif self.control_key:
                msg = self.spacing.cut_trim_left()
            elif self.alt_key:
                msg = self.spacing.cut_move_left()
            else:
                msg = self.spacing.cut_increment_cursor(-1)
            self.draw()
        elif event.key() == QtCore.Qt.Key_Right:
            if self.shift_key:
                msg = self.spacing.cut_widen_right()
            elif self.control_key:
                msg = self.spacing.cut_trim_right()
            elif self.alt_key:
                msg = self.spacing.cut_move_right()
            else:
                msg = self.spacing.cut_increment_cursor(1)
            self.draw()
        else:
            msg = 'You pressed an unrecognized key: '
            s = event.text()
            if len(s) > 0:
                msg += s
            else:
                msg += '%x' % event.key()
            event.ignore()
        if msg is not None:
            self.status_message(msg)

    def keyReleaseEvent(self, event):
        '''
        Handles key release events
        '''
        # return if not edit spacing
        if self.tabs_spacing.currentIndex() != self.edit_spacing_id:
            event.ignore()
            return

        if event.key() == QtCore.Qt.Key_Shift:
            self.shift_key = False
        elif event.key() == QtCore.Qt.Key_Control:
            self.control_key = False
        elif event.key() == QtCore.Qt.Key_Alt:
            self.alt_key = False
        else:
            event.ignore()
            if self.config.debug:
                print('you released %x' % event.key())

def run():
    '''
    Sets up and runs the application
    '''
    app = QtGui.QApplication(sys.argv)
#    app.setStyle('plastique')
#    app.setStyle('windows')
    app.setStyle('macintosh')
    driver = Driver()
    driver.show()
    driver.center()
    driver.raise_()
    app.exec_()

if __name__ == '__main__':
    run()
