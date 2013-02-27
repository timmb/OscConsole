#!/opt/local/bin/python
# -*- coding: utf-8 -*-
from osc.OSC import OSCServer
import sys
from PySide import QtGui, QtCore
from threading import Thread
import traceback


class OscConsole(QtGui.QWidget):
	def __init__(self):
		super(OscConsole, self).__init__()
		
		# self.buffer_length = 1000
		self.port_number = 37000
		# self.is_waiting_for_server_to_close = False

		self.messages = []
		self.messages_mutex = QtCore.QReadWriteLock()

		self.open_server()

		layout = QtGui.QVBoxLayout()

		self.console_box = QtGui.QPlainTextEdit(self)
		layout.addWidget(self.console_box)
		self.console_box.setReadOnly(True)
		self.console_box.setMaximumBlockCount(1000)
		# self.console_box.setCenterOnScroll(True)
		self.console_update_timer = QtCore.QTimer()
		self.console_update_timer.timeout.connect(self.check_to_update_console_box)
		self.console_update_timer.start(200)

		layout.addWidget(QtGui.QLabel('Listen to port: '))
		port_box = QtGui.QSpinBox(self)
		layout.addWidget(port_box)
		port_box.setMinimum(0)
		port_box.setMaximum(65535)
		port_box.setValue(self.port_number)
		port_box.setKeyboardTracking(False)
		port_box.valueChanged.connect(self.change_port)


		self.setLayout(layout)
		self.setWindowTitle('OSC Console')
		self.sizeHint = lambda: QtCore.QSize(450, 600)
		self.show()

	def log(self, string):
		self.add_message('*** '+string)

	def change_port(self, new_port_number):
		self.port_number = new_port_number
		self.open_server()

	def open_server(self):
		if hasattr(self, 'server') and self.server.running:
			self.close_server()
		self.log('Opening server on port {}'.format(self.port_number))
		try:
			self.server = OSCServer(('localhost',self.port_number))
			self.server.addMsgHandler('default', self.new_osc_message_callback)
			self.serverThread = Thread(target=self.server.serve_forever)
			self.serverThread.start()
		except Exception as e:
			self.log('Unable to open server on port {}. Possibly it is already open.'.format(self.port_number))
			self.log(str(e))

	def close_server(self):
		# self.is_waiting_for_server_to_close = True
		# self.log('Stopping server')
		self.server.running = False
		# self.log('Waiting for server thread to end')
		self.serverThread.join()
		# self.log('Closing server')
		self.server.close()
		# self.is_waiting_for_server_to_close = False

	def change_buffer_length(self, new_buffer_length):
		self.buffer_length = new_buffer_length

	def new_osc_message_callback(self, path, tags, args, source):
		# source path tags: args
		formatted_message = '{0[0]}:{0[1]} {1} ({2}): {3}'.format(
			source, path, tags, ', '.join(map(str,args)))
		self.add_message(formatted_message)

	def add_message(self, string):
		string = QtCore.QDateTime.currentDateTime().toString('hh:mm:ss')+' '+string
		scoped_lock = QtCore.QWriteLocker(self.messages_mutex)
		self.messages.append(string)
		if len(self.messages) > 1000:
			self.messages = self.messages[:1000]

	def check_to_update_console_box(self):
		if self.messages:
			scoped_lock = QtCore.QWriteLocker(self.messages_mutex)
			for message in self.messages:
				self.console_box.appendPlainText(message)
				cursor = self.console_box.textCursor()
				cursor.movePosition(QtGui.QTextCursor.End)
				self.console_box.setTextCursor(cursor)
			self.messages.clear()
			




def main():
	app = QtGui.QApplication(sys.argv)
	osc_console = OscConsole()
	return_code = app.exec_()
	osc_console.close_server()
	sys.exit(return_code)


if __name__ == '__main__':
	main()