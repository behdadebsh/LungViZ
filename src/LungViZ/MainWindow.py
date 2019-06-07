from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QToolTip, QMessageBox, QWidget, QAction, QMenu, QStatusBar, QVBoxLayout, QDialog, QTabWidget
import sys


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
        fileMenu.addAction(aboutButton)
        fileMenu.addAction(exitButton)

        self.setWindowIcon(QtGui.QIcon("Logo.jpeg"))
        button = QPushButton("Exit", self)
        button.move(700, 770)
        button.setToolTip("Closes the window")
        button.clicked.connect(self.Close)

        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.show()

        tabwidget = QTabWidget()
        tabwidget.addTab(Tab1(), "Tab1")
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


class TabWidget(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LungViZ")
        tabwidget = QTabWidget()
        tabwidget.addTab(Tab1(), "Tab1")
        vbox = QVBoxLayout()
        vbox.addWidget(tabwidget)
        self.setLayout(vbox)


class Tab1(QWidget):
    def __init__(self):
        super().__init__()


App = QApplication(sys.argv)
window = Window()
tabwidget = TabWidget()
tabwidget.show()
sys.exit(App.exec())
