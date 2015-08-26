# -*- coding: utf-8 -*-

from osc.OSC import OSCClient, OSCMessage

client = OSCClient()

def set_destination(host, port):
	client.connect((host, port))

def send(address_path, *args):
	message = OSCMessage(address_path)
	message.append(args)
	client.send(message)

set_destination('localhost', 5000)