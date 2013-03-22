#!/opt/local/bin/python
# -*- coding: utf-8 -*-
from osc.OSC import OSCServer, OSCClient, OSCMessage
import sys
from PySide import QtGui, QtCore
from threading import Thread
import traceback
import Queue as queue


class ThreadedSender(QtCore.QThread):
	def __init__(self, log_function, parent=None):
		QtCore.QThread.__init__(self, parent)
		self.is_running = False
		self._destination = ("127.0.0.1", 0)
		self.client = OSCClient()
		self.queue = queue.Queue()
		self.log = log_function

	def send(self, message):
		# assert(self.is_running)
		if not self.is_running: self.log("ERROR: Sender thread is not running")
		if self.is_running:
			self.queue.put(message)

	def close(self):
		self.is_running = False
		self.wait()

	def run(self):
		self.log("Starting Sender thread")
		self.is_running = True
		while self.is_running:
			try:
				message = self.queue.get(True, 0.1)
				self.client.sendto(message, self.destination, 0.5)
			except queue.Empty as e:
				pass
			except Exception as e:
				self.log("Unexpected exception when sending OSC message to"+str(self.destination)+": "+str(e))
		self.queue.queue.clear()
		self.log("Sender thread finished")




class OscConsole(QtGui.QWidget):
	def __init__(self):
		super(OscConsole, self).__init__()
		
		# self.buffer_length = 1000
		self.port_number = 37000
		self._forward_host = "127.0.0.1"
		self._forward_port = 37001
		self._enable_forwarding = False
		# self.is_waiting_for_server_to_close = False

		self.messages = []
		self.message_count = 0
		# self.messages_mutex = QtCore.QReadWriteLock()

		self.sender = ThreadedSender(self.log, self)
		self.sender.start()

		self.open_server()

		layout = QtGui.QVBoxLayout()

		self.console_box = QtGui.QPlainTextEdit(self)
		layout.addWidget(self.console_box)
		self.console_box.setReadOnly(True)
		self.console_box.setMaximumBlockCount(1000)
		self.console_box.setWordWrapMode(QtGui.QTextOption.NoWrap)
		# self.console_box.setCenterOnScroll(True)
		self.console_update_timer = QtCore.QTimer()
		self.console_update_timer.timeout.connect(self.check_to_update_console_box)
		self.console_update_timer.start(200)

		footer = QtGui.QHBoxLayout()
		layout.addLayout(footer)

		footer.addWidget(QtGui.QLabel('Listen to port: '))
		self.port_box = QtGui.QSpinBox(self)
		footer.addWidget(self.port_box)
		self.port_box.setMinimum(0)
		self.port_box.setMaximum(65535)
		self.port_box.setValue(self.port_number)
		self.port_box.setKeyboardTracking(False)
		self.port_box.valueChanged.connect(self.change_port)
		
		footer.addStretch()
		self.enable_forward_input = QtGui.QCheckBox("Forward input", self)
		footer.addWidget(self.enable_forward_input)
		self.enable_forward_input.setChecked(self.enable_forwarding)
		self.enable_forward_input.toggled.connect(self.set_enable_forwarding)

		layout.addWidget(QtGui.QLabel("Destination"))
		footer = QtGui.QHBoxLayout()
		layout.addLayout(footer)
		footer.addWidget(QtGui.QLabel("Address"))
		self.forward_host_input = QtGui.QLineEdit(self)
		footer.addWidget(self.forward_host_input)
		self.forward_host_input.setText(self.forward_host)
		self.forward_host_input.editingFinished.connect(self.set_forward_host)

		footer.addWidget(QtGui.QLabel("Port"))
		self.forward_port_input = QtGui.QSpinBox(self)
		footer.addWidget(self.forward_port_input)
		self.forward_port_input.setMinimum(0)
		self.forward_port_input.setMaximum(65535)
		self.forward_port_input.setValue(self.forward_port)
		self.forward_port_input.setKeyboardTracking(False)
		self.forward_port_input.valueChanged.connect(self.set_forward_port)

		# remember which gui elements are being updating to prevent recursion
		self.gui_elements_being_updated = []

		self.setLayout(layout)
		self.setWindowTitle('OSC Console')
		self.sizeHint = lambda: QtCore.QSize(450, 600)
		self.show()

	def update(self, gui_element, new_value, update_function='setValue'):
		'''Updates gui_element only if we are not already in the process
		of updating that element (i.e. this function prevents recursive 
		loops from Qt signaling when we update it).
		'''
		if gui_element not in self.gui_elements_being_updated:
			self.gui_elements_being_updated.append(gui_element)
			getattr(gui_element, update_function)(new_value)
			self.gui_elements_being_updated.remove(gui_element)

	@property
	def forward_host(self):
		return self._forward_host
	
	def set_forward_host(self, forward_host):
		if forward_host != self.forward_host:
			self._forward_host = forward_host.strip()
			# update gui
			self.update(self.forward_host_input, self.forward_host)
			self.change_enable_forwarding()

	@property
	def forward_port(self):
		return self._forward_port

	def set_forward_port(self, forward_port):
		if forward_port != self.forward_port:
			self._forward_port = forward_port
			self.update(self.forward_port_input, self.forward_port)
			self.change_enable_forwarding()

	@property
	def enable_forwarding(self):
		return self._enable_forwarding

	def set_enable_forwarding(self, enable_forwarding):
		if enable_forwarding != self.enable_forwarding:
			self._enable_forwarding = enable_forwarding
			self.update(self.enable_forward_input, self.enable_forwarding, 'setChecked')
			self.change_enable_forwarding()


	def change_enable_forwarding(self):
		if not self.enable_forwarding:
			return
		if (self.port_number == self.forward_port
			and self.self.forward_host_input in ('localhost', '127.0.0.1')):
			log("Error: Cannot forward to the same host and port as the one being listened to")
			self.enable_forwarding = False
		else:
			self.sender.destination = (self.forward_host, self.forward_port)


	def log(self, string):
		self.add_message('*** '+string)

	def change_port(self, new_port_number):
		self.port_number = new_port_number
		self.open_server()

	def open_server(self):
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

	def close(self):
		self.log("Closing server")
		self.close_server()
		self.log("Stopping sender thread")
		self.sender.close()

	def close_server(self):
		if not hasattr(self, 'server') or not self.server.running:
			return
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
		if self.enable_forwarding:
			message = OSCMessage(path)
			message.append(args)
			self.sender.send(message)

	def add_message(self, string):
		time = QtCore.QDateTime.currentDateTime().toString('hh:mm:ss')
		if self.message_count % 2:
			background_color = '#fff'
		else:
			background_color = '#e2dea7'
		# string = '<p style="background-color: {0};"> <span style="font-weight: bold">{1}</span> {2}</p>'.format(
			# background_color, time, string)
		string = '<span style="font-weight: bold">{1}</span> {2}</p>'.format(
			background_color, time, string)
		# print(string)
		# scoped_lock = QtCore.QWriteLocker(self.messages_mutex)
		self.messages.append(string)
		if len(self.messages) > 1000:
			self.messages = self.messages[:1000]
		self.message_count += 1

	def check_to_update_console_box(self):
		if self.messages:
			# scoped_lock = QtCore.QWriteLocker(self.messages_mutex)
			for message in self.messages:
				self.console_box.appendHtml(message)
				cursor = self.console_box.textCursor()
				cursor.movePosition(QtGui.QTextCursor.End)
				cursor.movePosition(QtGui.QTextCursor.StartOfLine)
				self.console_box.setTextCursor(cursor)
			self.messages = []
			




def main():
	args = sys.argv
	args[0] = "OSC Console"
	app = QtGui.QApplication(args)
	osc_console = OscConsole()
	return_code = app.exec_()
	osc_console.close()
	sys.exit(return_code)


if __name__ == '__main__':
	main()