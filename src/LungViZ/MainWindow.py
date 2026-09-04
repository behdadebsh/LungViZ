from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QToolTip, QMessageBox, QWidget, QAction, QMenu, QStatusBar, QVBoxLayout, QDialog, QTabWidget, QFileDialog
import sys
from PyQt5.uic import loadUi

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = "LungViZ"
        self.top = 200
        self.left = 500
        self.width = 800
        self.height = 800
        self.InitWindow()

    def InitWindow(self):

        self.statusBar = self.statusBar()
        self.statusBar.showMessage("LungViz is running")

        menubar = self.menuBar()
        fileMenu = menubar.addMenu("File")
        viewMenu = menubar.addMenu("View")
        toolsMenu = menubar.addMenu("Tools")
        helpMenu = menubar.addMenu("Help")

        aboutButton = QAction(QtGui.QIcon("about.png"), "About", self)
        aboutButton.triggered.connect(self.About)
        exitButton = QAction(QtGui.QIcon("exit.png"), "Exit", self)
        exitButton.triggered.connect(self.Close)
        viewCanvas = QAction(QtGui.QIcon(), "View Canvas", self)
        viewCanvas.triggered.connect(self.plot)
        loadDicom = QAction(QtGui.QIcon(), "Load Dicoms", self)
        loadDicom.triggered.connect(self.openbrowseUI)
        loadMask = QAction(QtGui.QIcon(), "Load masks", self)
        loadMask.triggered.connect(self.openbrowseUI)

        fileMenu.addAction(aboutButton)
        fileMenu.addAction(exitButton)
        viewMenu.addAction(viewCanvas)
        viewMenu.addAction(loadDicom)
        viewMenu.addAction(loadMask)

        self.setWindowIcon(QtGui.QIcon("Logo.jpeg"))
        button = QPushButton("Exit", self)
        button.move(700, 770)
        button.setToolTip("Closes the window")
        button.clicked.connect(self.Close)

        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.show()


        # tabwidget = QTabWidget()
        # tabwidget.addTab(Tab1(), "Tab1")
        # tabwidget.move(10, 10)
        # tabwidget.show()
        # vbox = QVBoxLayout()
        # vbox.addWidget(tabwidget)
        # self.setLayout(vbox)

    def Close(self):
        reply = QMessageBox.question(self, "Close Message", "Are you sure you want to quit? All unsaved data will be "
                                                            "lost.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close()

    def About(self):
        about = QMessageBox.about(self, "About Software", "LungViZ is under construction and licensed by Auckland"
                                                             "Bioengineering Institute, University of Auckland.")

    def plot(self):
        self.fig, self.ax = plt.subplots(1, 1)
        self.canvas = FigureCanvas(self.fig)

    def browsefiles(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file', '/hpc/bsha219')
        self.filename.setText(fname[0])

    def openbrowseUI(self):
        loadUi("browse-gui.ui",self)



# class TabWidget(QDialog):
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("LungViZ")
#         tabwidget = QTabWidget()
#         tabwidget.addTab(Tab1(), "Tab1")
#         vbox = QVBoxLayout()
#         vbox.addWidget(tabwidget)
#         self.setLayout(vbox)
#
#
# class Tab1(QWidget):
#     def __init__(self):
#         super().__init__()

class IndexTracker:
    def __init__(self, ax, X):
        self.ax = ax
        # ax.set_title('use scroll wheel to navigate images')

        self.X = X
        rows, cols, self.slices = X.shape
        self.ind = self.slices//2

        self.im = ax.imshow(self.X[:, :, self.ind])
        self.update()

    def on_scroll(self, event):
        print("%s %s" % (event.button, event.step))
        if event.button == 'up':
            self.ind = (self.ind + 1) % self.slices
        else:
            self.ind = (self.ind - 1) % self.slices
        self.update()

    def update(self):
        self.im.set_data(self.X[:, :, self.ind])
        self.ax.set_ylabel('slice %s' % self.ind)
        self.im.axes.figure.canvas.draw()


App = QApplication(sys.argv)
window = Window()
# tabwidget = TabWidget()
# tabwidget.show()
sys.exit(App.exec())
