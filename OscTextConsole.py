# -*- coding: utf-8 -*-

from osc.OSC import OSCServer, OSCClient, OSCMessage
import time
import sys

def message_callback(path, tags, args, source):
	t = time.strftime('%H:%M:%S')
	print('{0} {1[0]}:{1[1]} {2} ({3}): {4}'.format(
			t, source, path, tags, ', '.join(map(str,args))))

def main(listen_host, listen_port):
	print("Opening OSC Server on port {}".format(listen_port))
	server = OSCServer((listen_host, listen_port))
	server.addMsgHandler('default', message_callback)
	server.serve_forever()



if __name__ == '__main__':
	listen_port = int(sys.argv[1])
	listen_host = 'localhost'
	if (len(sys.argv) > 2):
		listen_host = sys.argv[2]
	main(listen_host, listen_port)