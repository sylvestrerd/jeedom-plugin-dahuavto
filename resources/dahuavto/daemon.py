#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from threading import Timer, Thread
from time import sleep

from vto_client import DahuaVTOClient

try:
    from jeedom.jeedom import *
except ImportError as e:
    print("Error: importing module from jeedom folder")
    print(traceback.format_exc())
    sys.exit(1)


DEVICES = {}

class DahuaVTOManager:
    def __init__(self, device):
        self._device = device

    def initialize(self):
        self._running = True
        while self._running:
            try:
                logging.info("Connecting")

                self._loop = asyncio.new_event_loop()

                client = self._loop.create_connection(
                    lambda: DahuaVTOClient(
                        self._device['host'],
                        self._device['username'],
                        self._device['password'],
                        self._device['protocole'],
                        self._device['port'],
                        self._device['model'],
                        self._message_received),
                    self._device['host'],
                    5000
                )
                self._loop.run_until_complete(client)
                self._loop.run_forever()
                self._loop.close()

                logging.warning("Disconnected, will try to connect in 5 seconds")

                sleep(5)

            except Exception as e:
                logging.error("Connection failed will try to connect in 30 seconds ({})".format(e))
                logging.debug(traceback.format_exc())

                sleep(30)

    def _message_received(self, message):
        logging.debug(message["Action"])
        #logging.debug(message)
        logging.debug("-------------------")

        messageData = message.get("Data", {})
        
        if message.get("Action") == "Start" and message.get("Code") == "CallNoAnswered":
            self._send_change({ 'calling': 1 })
            Timer(
                5,
                lambda: self._send_change({ 'calling': 0 }),
            ).start()
        
        if message.get("Action") == "Pulse" and message.get("Code") == "AccessControl" and messageData.get("Status") == 1:
            # "Index" is 0 or 1
            # 'unlocked' command is 1 or 2
            commandName = 'unlocked2' if message["Index"] == 1 else 'unlocked1'
            self._send_change({ commandName: 1 })

            Varmethod=self.methodedev(messageData.get("Method"))
            logging.debug(Varmethod)
            logging.debug("-------------------")
            if messageData.get('deviceType')=='DHI-VTO3221E-P':
                self._send_change({ 'typedev': Varmethod})
                self._send_change({ 'datederdev': messageData.get("LocaleTime")})
                self._send_change({ 'nbadge': messageData.get("CardNo")})
            
            Timer(
                10,
                lambda: self._send_change({ commandName: 0 }),
            ).start()
    
    def _send_change(self, params):
        JEEDOM_COM.add_changes("devices::{}".format(self._device['id']), params),

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running:
            self._loop.stop()

    def methodedev(self,i):
        switcher={
                0:'Dévérouillage par clavier',
                4:'Dévérouillage par DMSS',
                1:'Dévérouillage par badge'
             }
        return switcher.get(i,"")

def read_socket(name):
    should_stop = False
    while not should_stop:
        try:
            global JEEDOM_SOCKET_MESSAGE
            if not JEEDOM_SOCKET_MESSAGE.empty():
                logging.debug("Message received in socket JEEDOM_SOCKET_MESSAGE")
                message = JEEDOM_SOCKET_MESSAGE.get().decode('utf-8')
                message = json.loads(message)
                if message['apikey'] != _apikey:
                    logging.error("Invalid apikey from socket : {}".format(str(message)))
                    return
                logging.debug('Received command from jeedom : {}'.format(str(message['cmd'])))

                if message['cmd'] == 'add':
                    if 'id' in message['device']:
                        logging.debug('Add device : {}'.format(str(message['device']['id'])))
                        if message['device']['id'] in DEVICES:
                            DEVICES[message['device']['id']]['manager'].stop()

                        device = DEVICES[message['device']['id']] = message['device']

                        # Start manager
                        device['manager'] = DahuaVTOManager(device)
                        threading.Thread(target=device['manager'].initialize).start()
                            
                elif message['cmd'] == 'remove':
                    logging.debug('Remove device : {}'.format(str(message['device'])))
                    if message['device']['id'] in DEVICES:
                        DEVICES[message['device']['id']]['manager'].stop()
                        del DEVICES[message['device']['id']]
                        
                elif message['cmd'] == 'stop':
                    logging.info('Stop the daemon required by socket')
                    logging.info('Closing devices threads...')
                    for device in DEVICES:
                        if 'manager' in device:
                            device['manager'].stop()
                    should_stop = True
        except Exception as e:
            logging.error("Exception on socket : {}".format(e))
            logging.debug(traceback.format_exc())
        sleep(0.3)
    
    shutdown()
  

def shutdown():
	logging.debug("Shutdown")
	logging.debug("Removing PID file {}".format(str(_pidfile)))
	try:
		os.remove(_pidfile)
	except:
		pass
	try:
		jeedom_socket.close()
	except:
		pass
	logging.debug("Exit 0")
	sys.stdout.flush()
	os._exit(0)

_log_level = 'error'
_socket_port = 55009
_socket_host = 'localhost'
_pidfile = '/tmp/vahuadto.pid'
_apikey = ''
_callback = ''
_daemon_name = ''
_cycle = 0


parser = argparse.ArgumentParser(description='dahuavto daemon for Jeedom plugin')
parser.add_argument("--loglevel", help="Log Level for the daemon", type=str)
parser.add_argument("--pidfile", help="Value to write", type=str)
parser.add_argument("--callback", help="Value to write", type=str)
parser.add_argument("--apikey", help="Value to write", type=str)
parser.add_argument("--socketport", help="Socket Port", type=str)
parser.add_argument("--sockethost", help="Socket Host", type=str)
parser.add_argument("--daemonname", help="Daemon Name", type=str)
parser.add_argument("--cycle", help="Cycle to send event", type=str)

args = parser.parse_args()

if args.loglevel and args.loglevel != "none":
    _log_level = args.loglevel
if args.pidfile:
    _pidfile = args.pidfile
if args.callback:
    _callback = args.callback
if args.apikey:
    _apikey = args.apikey
if args.cycle:
    _cycle = float(args.cycle)
if args.socketport:
	_socket_port = args.socketport
if args.sockethost:
	_socket_host = args.sockethost
if args.daemonname:
    _daemon_name = args.daemonname

_socket_port = int(_socket_port)
_cycle = float(_cycle)

jeedom_utils.set_log_level(_log_level)
logging.info('Starting Dahua VTO daemon...')

logging.debug("log_level: {}".format(_log_level))
logging.debug("pidfile: {}".format(_pidfile))
logging.debug("callback: {}".format(_callback))
logging.debug("apikey: {}".format(_apikey))
logging.debug("cycle: {}".format(_cycle))
logging.debug("socket_port: {}".format(_socket_port))
logging.debug("socket_host: {}".format(_socket_host))
logging.debug("daemon_name: {}".format(_daemon_name))

try:
    jeedom_utils.write_pid(str(_pidfile))
    JEEDOM_COM = jeedom_com(apikey = _apikey,url = _callback,cycle=_cycle)

    if not JEEDOM_COM.test():
        logging.error('Network communication issues. Please fix your Jeedom network configuration.')
        shutdown()

    jeedom_socket = jeedom_socket(port=_socket_port,address=_socket_host)
    jeedom_socket.open()
    Thread(target=read_socket, args=('socket',)).start()
except Exception as e:
    logging.error('Fatal error : {}'.format(str(e)))
    logging.debug(traceback.format_exc())
    shutdown()
