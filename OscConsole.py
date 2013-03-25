#!/opt/local/bin/python
# -*- coding: utf-8 -*-
from osc.OSC import OSCServer, OSCClient, OSCMessage
import sys
from PySide import QtGui, QtCore
from threading import Thread
import traceback
import Queue as queue
import UX.MainWindow
from time import time
import re


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


class LogPlayer(QtCore.QThread):
	def __init__(self, log_function, osc_message_callback, parent=None):
		super(LogPlayer, self).__init__(parent)
		self.log = log_function
		self.osc_message_callback = osc_message_callback
		self.messages = [] # (float_time, (path, tags, args, source))
		self.new_playback_time_callbacks = []
		self.new_start_time_callbacks = []
		self.new_end_time_callbacks = []
		self.new_state_callbacks = []
		# all times are calculated as seconds since midnight
		self.time_of_first_message_in_log = 0.
		self.time_of_last_message_in_log = 0.
		self._requested_start_time = 0.
		self._requested_end_time = 0.
		# invar: self.messages[self.current_playback_index][0] >= self.current_playback_time
		self._current_playback_time = None
		self.current_playback_index = 0
		self._state = 'stopped'
		self._inside_tick = False

	@property
	def current_playback_time(self):
		if self._current_playback_time==None:
			return self.requested_start_time
		else:
			return self._current_playback_time

	@current_playback_time.setter
	def current_playback_time(self, x):
		self._current_playback_time = x
		for f in self.new_playback_time_callbacks:
			f(self.current_playback_time)

	@property
	def requested_start_time(self):
		return self._requested_start_time

	@requested_start_time.setter
	def requested_start_time(self, x):
		self._requested_start_time = x
		for f in self.new_start_time_callbacks:
			f(x)
		if self._current_playback_time==None:
			for f in self.new_playback_time_callbacks:
				f(self.current_playback_time)

	@property
	def requested_end_time(self):
		return self._requested_end_time

	@requested_end_time.setter
	def requested_end_time(self, x):
		self._requested_end_time = x
		for f in self.new_end_time_callbacks:
			f(x)

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, x):
		self._state = x
		for f in self.new_state_callbacks:
			f(x)

	def open(self, filename):
		self.stop()
		try:
			with open(filename, 'r') as f:
				self.messages = []
				pattern = re.compile(r'''
					(?P<hours>\d\d)
					:
					(?P<minutes>\d\d)
					:
					(?P<seconds>\d\d)
					\.
					(?P<milliseconds>\d\d\d)
					\ # The time
					(?P<source>\S*)
					\ # The source (e.g. "127.0.0.1:49612 ")
					(?P<address>\S*)
					\ # The address string (e.g. "/hello ")
					\((?P<tag>\w*)\)
					:\ # The tag patter (e.g. "(siii): ")
					(?P<args>[^\Z]*) 
					# Match up until the end of the string
					''', re.VERBOSE)
				comment_pattern = re.compile(r'''
					(?P<hours>\d\d)
					:
					(?P<minutes>\d\d)
					:
					(?P<seconds>\d\d)
					\.
					(?P<milliseconds>\d\d\d)
					\ \*\*\*\ # The time
					(?P<comment>[^Z]*)
					''', re.VERBOSE)
				for line in f:
					match = pattern.match(line)
					if match:
						try:
							hours = int(match.group('hours'))
							minutes = int(match.group('minutes'))
							seconds = int(match.group('seconds'))
							millis = int(match.group('milliseconds'))
							source = match.group('source')
							address = match.group('address')
							raw_tag = list(match.group('tag'))
							raw_args = (x.strip() for x in match.group('args').split(', '))
							tags = ''
							args = []
							for tag,arg in zip(raw_tag, raw_args):
								tags += tag
								if tag in ('i','h'):
									args.append(int(arg))
								elif tag in ('s','S','b'):
									args.append(arg)
								elif tag in ('f','d'):
									args.append(float(arg))
								else:
									tags = tags[:-1]
									self.log("Unrecognised type tag: "+tag)
							t = 3600*hours + 60*minutes + seconds + 0.001*millis
							self.messages.append((t, (address, tags, args, source)))
							# print(self.messages[-1])
						except Exception as e:
							self.log("Problem when parsing line "+line+"\n"+str(e))
					else:
						match = comment_pattern.match(line)
						if match:
							try:
								hours = int(match.group('hours'))
								minutes = int(match.group('minutes'))
								seconds = int(match.group('seconds'))
								millis = int(match.group('milliseconds'))
								comment = match.group('comment')
								self.log(comment, screen_only=True)
							except Exception as e:
								self.log("Problem when parsing comment line "+line+"\n"+str(e))
						else:
							self.log("Unable to parse line: '"+line+"', skipping.")
				if self.messages:
					self.time_of_first_message_in_log = self.messages[0][0]
					self.time_of_last_message_in_log = self.messages[-1][0]+1
				else:
					self.time_of_first_message_in_log = 0
					self.time_of_last_message_in_log = 0
			self.requested_start_time = self.time_of_first_message_in_log
			self.requested_end_time = self.time_of_last_message_in_log
			self.current_playback_time = None
		except IOError as e:
			self.log("Error opening file "+filename+"\n"+str(e))

	def run(self):
		self.exec_()

	def tick(self):
		if self._inside_tick:
			return
		self._inside_tick = True
		if self.state == 'playing':
			t = time()
			dt = t - self.time_of_last_tick
			self.current_playback_time += dt
			while (self.current_playback_index < len(self.messages)
				and self.messages[self.current_playback_index][0] < self.current_playback_time):
				self.process_message(self.messages[self.current_playback_index])
				self.current_playback_index += 1
			if self.current_playback_time > self.requested_end_time:
				self.stop("Reached end of requested playback period")
			if self.current_playback_index >= len(self.messages):
				self.stop("Reached end of log file")
			self.time_of_last_tick = t
		self._inside_tick = False

	def process_message(self, message):
		print('processing message '+str(message))
		self.osc_message_callback(*message[1], time_override=seconds_to_qtime(message[0]))

	def play(self):
		self.time_of_last_tick = time()
		if self.state=='stopped':
			self.current_playback_index = len([x for x in self.messages if x[0]<self.current_playback_time])
			self.ticker = QtCore.QTimer(self)
			self.ticker.timeout.connect(self.tick)
			self.ticker.start(1)
			self.start()
		self.state = 'playing'
	

	def pause(self):
		self.state = 'paused'

	def stop(self, message=""):
		if self.state != 'stopped':
			self.ticker.stop()
			m = "Stopping playback"+(message and (": "+message) or "")
			print(m)
			self.log(m, True)
			print('calling exit()')
			self.exit()
			print('exited')
			self.state = 'stopped'
		self.current_playback_time = self.requested_start_time


class OscConsole(QtGui.QApplication):
	def __init__(self, argv):
		super(OscConsole, self).__init__(argv)
		self.port_number = 37000
		self._forward_host = "127.0.0.1"
		self._forward_port = 37001
		self._enable_forwarding = False
		self.playback_file = None
		self.mode = ''
		self.playback_time = None
		self.playback_start_time = None
		self.playback_end_time = None

		self.messages = []
		self.message_count = 0
		self.messages_to_print = queue.Queue(50)

		self.sender = ThreadedSender(self.log, self)
		self.sender.start()

		self.log_player = LogPlayer(self.log, self.new_osc_message_callback)

		self.change_mode('live')
		self.aboutToQuit.connect(self.close)

	def change_mode(self, new_mode):
		if new_mode == self.mode:
			return
		if new_mode == 'live':
			self.log("Changing mode: live")
			self.log_player.stop()
			self.open_server()
		if new_mode == 'playback':
			self.log("Changing mode: playback")
			self.close_server()

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

	def log(self, string, screen_only=False, time_override=None):
		'''time_override may be QTime object. '''
		self.add_message('*** '+string, screen_only, time_override=time_override)

	def change_port(self, new_port_number):
		if self.port_number==new_port_number:
			return
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
		self.close_server()
		self.log("Stopping sender thread")
		self.sender.close()

	def close_server(self):
		self.log("Closing server")
		if not hasattr(self, 'server') or not self.server.running:
			return
		self.server.running = False
		self.serverThread.join()
		self.server.close()

	def new_osc_message_callback(self, path, tags, args, source, time_override=None):
		# source path tags: args
		formatted_message = '{0[0]}:{0[1]} {1} ({2}): {3}'.format(
			source, path, tags, ', '.join(map(str,args)))
		self.add_message(formatted_message, time_override=time_override)
		if self.enable_forwarding:
			message = OSCMessage(path)
			message.append(args)
			self.sender.send(message)

	def add_message(self, string, screen_only=False, time_override=None):
		time_override = time_override or QtCore.QDateTime.currentDateTime()
		time = time_override.toString('hh:mm:ss.zzz')
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
		self.saved_file = ""
		self.opened_file = ""

		self.ui.liveOrPlaybackButtonGroup.setId(self.ui.liveRadio, 0)
		self.ui.liveOrPlaybackButtonGroup.setId(self.ui.playbackRadio, 1)
		self.ui.actionQuit.triggered.connect(QtGui.QApplication.instance().quit)
		self.ui.actionSaveAs.triggered.connect(self.save_as)
		self.ui.actionOpen.triggered.connect(self.open)
		self.ui.playbackFileOpenButton.clicked.connect(self.ui.actionOpen.trigger)
		self.ui.playbackFileInput.editingFinished.connect(lambda: self.open_file(self.ui.playbackFileInput.text()))
		self.ui.playOrPauseButton.clicked.connect(self.play_or_pause_button)
		self.ui.stopButton.clicked.connect(self.stop_button)
		self.ui.playbackTimeInput.editingFinished.connect(self.change_playback_time)
		self.ui.startTimeInput.editingFinished.connect(self.change_start_time)
		self.ui.endTimeInput.editingFinished.connect(self.change_end_time)
		self.ui.startTimeResetButton.clicked.connect(self.reset_start_time)
		self.ui.endTimeResetButton.clicked.connect(self.reset_end_time)
		self.ui.loopPlaybackInput.toggled.connect(self.change_loop_playback)

		self.app.log_player.new_playback_time_callbacks.append(
			lambda s: self.time_changed_callback(self.ui.playbackTimeInput, s))
		self.app.log_player.new_start_time_callbacks.append(
			lambda s: self.time_changed_callback(self.ui.startTimeInput, s))
		self.app.log_player.new_end_time_callbacks.append(
			lambda s: self.time_changed_callback(self.ui.endTimeInput, s))
		self.app.log_player.new_state_callbacks.append(self.state_changed_callback)

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

	def change_listening_port(self):
		self.app.change_port(self.ui.listeningPortInput.value())

	def change_output_port(self):
		value = self.ui.outputPortInput.value()
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
		self.app.change_mode('live')

	def change_to_playback_mode(self):
		self.app.change_mode('playback')

	def play_or_pause_button(self):
		if self.app.log_player.state == 'playing':
			self.app.log_player.pause()
			self.ui.playOrPauseButton.setText("Play (Space)")
		else:
			self.app.log_player.play()
			self.ui.playOrPauseButton.setText("Pause (Esc)")

	def stop_button(self):
		self.app.log_player.stop()

	def change_playback_time(self):
		self.app.log_player.set_playback_time(qtime_to_seconds(self.ui.startTimeInput.time()))

	def change_start_time(self):
		self.app.log_player.requested_start_time = qtime_to_seconds(self.ui.startTimeInput.time())

	def change_end_time(self):
		self.app.log_player.requested_end_time = qtime_to_seconds(self.ui.startTimeInput.time())

	def change_loop_playback(self, value):
		print("loop not implemented yet")

	def reset_start_time(self):
		self.app.log_player.requested_start_time = self.app.log_player.time_of_first_message_in_log

	def reset_end_time(self):
		self.app.log_player.requested_start_time = self.app.log_player.time_of_last_message_in_log

	def save_as(self):
		new_save_file = QtGui.QFileDialog.getSaveFileName(self, "Save log data", 
			self.saved_file, "OSC Logs (*.oscLog)")[0]
		if new_save_file:
			self.saved_file = new_save_file
			self.app.save_log(self.saved_file)

	def open(self):
		self.open_file(QtGui.QFileDialog.getOpenFileName(self, "Open log file",
			self.opened_file[:self.opened_file.rfind('/')], "OSC Logs (*.oscLog)")[0])

	def open_file(self, new_file):
		if new_file:
			self.opened_file = new_file
			self.app.log_player.open(self.opened_file)
			self.update(self.ui.playbackFileInput, self.opened_file, 'setText')
			self.ui.playbackRadio.click()

	def time_changed_callback(self, time_input, new_value_in_seconds):
		t = seconds_to_qtime(new_value_in_seconds)
		self.update(time_input, t, 'setTime')

	def state_changed_callback(self, new_state):
		if new_state!='playing':
			self.ui.playOrPauseButton.setText('Play (Space)')
		else:
			self.ui.playOrPauseButton.setText('Pause (Space)')

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
			


def qtime_to_seconds(value):
	return abs(value.secsTo(QtCore.QTime(0,0)))

def seconds_to_qtime(value):
	return QtCore.QTime(0,0).addSecs(int(value))





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