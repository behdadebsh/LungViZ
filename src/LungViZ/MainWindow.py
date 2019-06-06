from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QMainWindow
import sys


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = "LungViZ"
        self.top = 200
        self.left = 500
        self.width = 400
        self.height = 300
        self.InitWindow()

    def InitWindow(self):
        self.setWindowIcon(QtGui.QIcon("Logo.jpeg"))
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.show()


App = QApplication(sys.argv)
window = Window()
sys.exit(App.exec())
