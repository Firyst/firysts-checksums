# -*- coding: utf-8 -*-
from PyQt5 import uic, QtCore, QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog, QVBoxLayout, QLabel, QWidget, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import sys
import hashlib
import os
import time
import importlib
import random
from PyQt5 import QtGui


class InputError(Exception):
    """Just a custom exception for bad input file"""
    pass


def parse_check_file(filepath):
    """Open file and try to parse files and checksums"""
    output = dict()  # dict{filepath: checksum, ...}

    with open(filepath, 'r', encoding="utf8") as file:
        lines = file.read().split("\n")  # parse all the lines
        for i, line in enumerate(lines):

            if not line or line[0] == ';':
                # check if line is empty or is a comment
                continue

            splitline = line.split(" ")
            # check if seems to be valid
            if len(splitline) > 1:
                # note file in the result
                output[' '.join(splitline[1:]).replace('*', '', 1)] = splitline[0]
            else:
                raise InputError(f"Bad line {i}")

    return output


def file_md5(filepath):
    """Read file and calculate MD5 chechsum"""
    try:
        with open(filepath, "rb") as f:
            file_hash = hashlib.md5()
            while chunk := f.read(16384):
                file_hash.update(chunk)
    except Exception as e:
        print(e)

    return file_hash.hexdigest()


class Dialog1(QDialog):

    def __init__(self):

        super().__init__()
        uic.loadUi('res/end_dialog.ui', self)  # загрузка UI файла
        self.setWindowFlags(Qt.WindowContextHelpButtonHint ^ self.windowFlags())

    def close_dialog(self):
        self.close()


class FileCheckerThread(QtCore.QThread):
    checked_signal = QtCore.pyqtSignal(str)
    target = ""

    def __init__(self, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.parent_window = parent

    def run(self):
        self.checked_signal.emit(file_md5(self.target))


class ProgramWindow(QMainWindow):
    """! Main program window
    """

    def __init__(self):
        # load UI
        super().__init__()
        uic.loadUi('main.ui', self)

        self.bind_actions()

        # checker data
        self.file_list = []  # all file path
        self.file_dict = dict()  # dict{filepath: checksum}
        self.file_index = 0  # current file index in file_list
        self.file_status = {"pass": 0, "missing": 0, "bad": 0}
        self.state = {"pass": 1, "missing": 1, "bad": 1}

        # thread
        self.worker_thread = FileCheckerThread(self)
        self.worker_thread.checked_signal.connect(self.file_checked_event)

        # working data
        self.cwd = ""  # current working directory
        self.output_file = ""

        # bind checkboxes
        temp = lambda: self.reload_log(self.check_passed.isChecked(), self.check_missing.isChecked(),
                                       self.check_bad.isChecked())
        self.check_passed.stateChanged.connect(temp)
        self.check_missing.stateChanged.connect(temp)
        self.check_bad.stateChanged.connect(temp)

        self.stacked_widget.setCurrentIndex(0)

    def bind_actions(self):
        # bind all button actions at setup.
        self.button_open.clicked.connect(self.select_file_to_open)
        self.button_create.clicked.connect(self.select_folder_to_list)

    def file_checked_event(self, result: str):
        if result == "FILE_MISSING":
            self.write_log(f"MISSING {self.file_list[self.file_index]}", self.state["missing"])
            self.file_status["missing"] += 1
        else:
            if result == self.file_dict[self.file_list[self.file_index]]:
                # file ok
                self.write_log(f"PASS {self.file_list[self.file_index]}", self.state["pass"])
                self.file_status["pass"] += 1
            else:
                self.write_log(f"BAD {self.file_list[self.file_index]}", self.state["bad"])
                self.file_status["bad"] += 1
        self.file_index += 1
        self.run_file_check()

        self.label_check_files.setText(f"Files: {self.file_index}/{len(self.file_list)}")  # summary text
        self.progress_bar_check.setValue(int(100 * self.file_index / len(self.file_list)))  # progress bar
        self.label_checks.setText(f"Pass: {self.file_status['pass']}    "
                                  f"Bad: {self.file_status['bad']}    "
                                  f"Missing: {self.file_status['missing']}")

    def run_file_check(self):
        if self.file_index >= len(self.file_list):
            # all files checked
            # QMessageBox.about(self, "Done", "Check finished")
            return
        filepath = self.file_list[self.file_index]
        if os.path.exists(filepath):
            self.worker_thread.target = filepath
            self.worker_thread.start()
        else:
            self.file_checked_event("FILE_MISSING")

    def write_log(self, line, w):
        with open(os.path.join(self.cwd, "checker_log.txt"), 'a+', encoding="utf8") as f:
            f.write('\n')
            f.write(line)
        if w:
            self.check_log.appendPlainText(line)

    def reload_log(self, good, miss, bad):
        """Reloads log with given filters"""
        self.state = {"pass": self.check_passed.isChecked(),"missing": self.check_missing.isChecked(), "bad": self.check_bad.isChecked()}
        self.check_log.setPlainText("-= Firyst's checksums v1.0 =-")  # clean log
        with open(os.path.join(self.cwd, "checker_log.txt"), 'r', encoding="utf8") as f:
            lines = f.read().split('\n')
        for line in lines:
            split_line = line.split()
            if len(split_line) > 1:
                # check log lines for ones we need to write
                if split_line[0] == "PASS" and good:
                    self.check_log.appendPlainText(line)
                elif split_line[0] == "MISSING" and miss:
                    self.check_log.appendPlainText(line)
                elif split_line[0] == "BAD" and bad:
                    self.check_log.appendPlainText(line)

    def select_file_to_open(self):
        dialog = QFileDialog(self, "Select file")
        if dialog.exec_():
            try:
                # try parsing checksums file
                files = parse_check_file(dialog.selectedFiles()[0])
                if len(files) == 0:
                    raise InputError("Error parsing file")
                self.file_list = list(files.keys())
                self.file_dict = files
                self.file_index = 0

                # everything is ok, ready to go!
                # connect event to checker
                self.worker_thread.checked_signal.disconnect()
                self.worker_thread.checked_signal.connect(self.file_checked_event)

                self.file_status = {"pass": 0, "missing": 0, "bad": 0}
                self.cwd = os.path.dirname(dialog.selectedFiles()[0])
                with open(os.path.join(self.cwd, "checker_log.txt"), 'w+', encoding="utf8") as f:
                    f.write("-= Firyst's checksums v1.0 =-")

                os.chdir(self.cwd)

                self.stacked_widget.setCurrentIndex(1)
                self.run_file_check()
                self.label_check_files.setText(f"Files: 0/{len(self.file_list)}")
            except InputError as exc:
                pass

    def select_folder_to_list(self):
        folder = QFileDialog(self).getExistingDirectory(self, "Select folder to scan")
        print(folder)
        if folder:
            # folder selected!
            self.file_index = 0
            self.cwd = folder + "/"
            os.chdir(self.cwd)
            self.file_list = []

            # reconnect event to read event
            self.worker_thread.checked_signal.disconnect()
            self.worker_thread.checked_signal.connect(self.file_read_event)

            self.stacked_widget.setCurrentIndex(2)

            for root, dirnames, filenames in os.walk(folder):
                for filename in filenames:
                    self.file_list.append(os.path.relpath(os.path.join(root, filename), self.cwd))

            self.label_create_files.setText(f"Files: 0/{len(self.file_list)}")

            with open(os.path.join(self.cwd, "files_checksum.md5"), 'w+', encoding="utf8") as f:
                f.write("; Generated by Firyst's checksums v1.0\n; Thanks)")

            self.run_file_read()

    def file_read_event(self, result):
        with open(os.path.join(self.cwd, "files_checksum.md5"), 'a+', encoding="utf8") as f:
            f.write('\n' + result + " *" + self.file_list[self.file_index])

        self.create_log.appendPlainText(f"{result} \t{self.file_list[self.file_index]}")
        self.file_index += 1
        self.label_create_files.setText(f"Files: {self.file_index}/{len(self.file_list)}")  # summary text
        self.progress_bar_create.setValue(int(100 * self.file_index / len(self.file_list)))  # progress bar
        self.run_file_read()

    def run_file_read(self):
        if self.file_index >= len(self.file_list):
            # all files checked
            print("done")
            self.create_log.appendPlainText(f"Done! File saved to: {self.cwd}/files_checksum.md5")
            return
        filepath = self.file_list[self.file_index]

        self.worker_thread.target = filepath
        self.worker_thread.start()

    def select_output_file(self):
        self.output_file = QFileDialog(self, "Select file").getSaveFileName(self, "Save output")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ProgramWindow()
    win.show()
    sys.exit(app.exec_())
