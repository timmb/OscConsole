#!/opt/local/bin/python
# -*- coding: utf-8 -*-
from osc.OSC import OSCServer, OSCClient, OSCMessage
import sys
from PySide import QtGui, QtCore
from threading import Thread
import traceback
import Queue as queue
import UX.MainWindow


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


class OscConsole(QtGui.QApplication):
	def __init__(self, argv):
		super(OscConsole, self).__init__(argv)
		self.port_number = 37000
		self._forward_host = "127.0.0.1"
		self._forward_port = 37001
		self._enable_forwarding = False
		self.playback_file = None
		self.mode = 'live'
		self.playback_time = None
		self.playback_start_time = None
		self.playback_end_time = None

		self.messages = []
		self.message_count = 0
		self.messages_to_print = queue.Queue(50)

		self.sender = ThreadedSender(self.log, self)
		self.sender.start()

		self.open_server()
		self.aboutToQuit.connect(self.close)

	@property
	def forward_host(self):
		return self._forward_host
	
	def set_forward_host(self, forward_host):
		if forward_host != self.forward_host:
			self._forward_host = forward_host.strip()
			# update gui
			self.update_forwarding_settings()

	@property
	def forward_port(self):
		return self._forward_port

	def set_forward_port(self, forward_port):
		if forward_port != self.forward_port:
			self._forward_port = forward_port
			self.update_forwarding_settings()

	@property
	def enable_forwarding(self):
		return self._enable_forwarding

	def set_enable_forwarding(self, enable_forwarding):
		if enable_forwarding != self.enable_forwarding:
			self._enable_forwarding = enable_forwarding
			self.update_forwarding_settings()


	def update_forwarding_settings(self):
		if not self.enable_forwarding:
			return
		if (self.port_number == self.forward_port
			and self.forward_host in ('localhost', '127.0.0.1')):
			log("Error: Cannot forward to the same host and port as the one being listened to")
			self.enable_forwarding = False
		else:
			self.sender.destination = (self.forward_host, self.forward_port)

	def log(self, string, screen_only=False):
		self.add_message('*** '+string, screen_only)

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
		self.server.running = False
		self.serverThread.join()
		self.server.close()

	def new_osc_message_callback(self, path, tags, args, source):
		# source path tags: args
		formatted_message = '{0[0]}:{0[1]} {1} ({2}): {3}'.format(
			source, path, tags, ', '.join(map(str,args)))
		self.add_message(formatted_message)
		if self.enable_forwarding:
			message = OSCMessage(path)
			message.append(args)
			self.sender.send(message)

	def add_message(self, string, screen_only=False):
		time = QtCore.QDateTime.currentDateTime().toString('hh:mm:ss.zzz')
		# if self.message_count % 2:
		# 	background_color = '#fff'
		# else:
		# 	background_color = '#e2dea7'
		# string = '<p style="background-color: {0};"> <span style="font-weight: bold">{1}</span> {2}</p>'.format(
			# background_color, time, string)
		# scoped_lock = QtCore.QWriteLocker(self.messages_mutex)
		formatted_string = '<span style="font-weight: bold;">{0}</span> {1}</p>'.format(
			time, string)
		if screen_only:
			formatted_string = '<span style="color: #f32;">'+formatted_string+'</span>'
		if not screen_only:
			unformatted_string = '{0} {1}'.format(time, string)
			self.messages.append(unformatted_string)
		try:
			self.messages_to_print.put_nowait(formatted_string)
		except queue.Full as e:
			print("Warning: console buffer full")

		if len(self.messages) > 250000:
			self.messages = self.messages[:245000]
		self.message_count += 1

	def save_log(self, filename):
		self.log("Saving to {}...".format(filename), screen_only=True)
		with open(filename, 'w') as out:
			for string in self.messages:
				out.write(string)
				out.write('\n')
			self.log("Successfully saved "+filename.split('/')[-1], screen_only=True)


class MainWindow(QtGui.QMainWindow):
	def __init__(self, main_application):
		super(MainWindow, self).__init__()
		self.app = main_application
		self.ui = UX.MainWindow.Ui_MainWindow()
		self.ui.setupUi(self)

		self.console_update_timer = QtCore.QTimer()
		self.console_update_timer.timeout.connect(self.check_to_update_console_box)
		self.console_update_timer.start(200)

		self.ui.listeningPortInput.setValue(self.app.port_number)
		self.ui.listeningPortInput.editingFinished.connect(self.change_listening_port)
		
		self.ui.enableOutputInput.setChecked(self.app.enable_forwarding)
		self.ui.enableOutputInput.toggled.connect(self.change_enable_output)

		self.ui.outputAddressInput.setText(self.app.forward_host)
		self.ui.outputAddressInput.editingFinished.connect(self.change_output_host)

		self.ui.outputPortInput.setValue(self.app.forward_port)
		self.ui.outputPortInput.editingFinished.connect(self.change_output_port)

		# remember which gui elements are being updating to prevent recursion
		self.gui_elements_being_updated = []
		self.save_file = ""

		self.ui.liveOrPlaybackButtonGroup.setId(self.ui.liveRadio, 0)
		self.ui.liveOrPlaybackButtonGroup.setId(self.ui.playbackRadio, 1)
		self.ui.actionQuit.triggered.connect(QtGui.QApplication.instance().quit)
		self.ui.actionSaveAs.triggered.connect(self.save_as)
		self.ui.liveOrPlaybackButtonGroup.buttonClicked[int].connect(self.ui.liveOrPlaybackPages.setCurrentIndex)

		self.ui.livePage.layout().setAlignment(QtCore.Qt.AlignTop)

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

	def change_listening_port(self, value):
		self.app.change_port(value)

	def change_output_port(self, value):
		self.app.set_forward_port(value)
		if (self.app.forward_port != value):
			self.update(self.ui.outputPortInput, value)

	def change_output_host(self, value):
		self.app.set_forward_host(value)
		if (self.app.forward_host != value):
			self.update(self.ui.outputHostInput, value, 'setText')

	def change_enable_output(self, value):
		self.app.set_enable_forwarding(value)
		if (self.app.enable_forwarding != value):
			self.update(self.ui.enableOutputInput, value, 'setChecked')

	def change_to_live_mode(self):
		pass

	def change_to_playback_mode(self):
		pass

	def play_or_pause_button(self):
		pass

	def stop_button(self):
		pass

	def change_playback_time(self, value):
		pass

	def change_start_time(self, value):
		pass

	def change_end_time(self, value):
		pass

	def change_loop_playback(self, value):
		pass

	def reset_start_time(self):
		pass

	def reset_end_time(self):
		pass

	def save_as(self):
		new_save_file = QtGui.QFileDialog.getSaveFileName(self, "Save log data", 
			self.save_file, "OSC Logs (*.oscLog)","OSC Logs (*.oscLog)")[0]
		if new_save_file:
			self.save_file = new_save_file
			self.app.save_log(self.save_file)


	def check_to_update_console_box(self):
		while not self.app.messages_to_print.empty():
			try:
				message = self.app.messages_to_print.get(False)
			except queue.Empty:
				break
			self.ui.console.appendHtml(message)
			cursor = self.ui.console.textCursor()
			cursor.movePosition(QtGui.QTextCursor.End)
			cursor.movePosition(QtGui.QTextCursor.StartOfLine)
			self.ui.console.setTextCursor(cursor)
			




def main():
	argv = sys.argv
	argv[0] = "OSC Console"
	app = OscConsole(argv)
	main_Window = MainWindow(app)
	return_code = app.exec_()
	app.close()
	sys.exit(return_code)


if __name__ == '__main__':
	main()