#!/usr/bin/env python3

import asyncio
import hashlib
import json
import logging
import sys
from threading import Timer
from typing import Optional

import requests
from requests.auth import HTTPDigestAuth

from messages import MessageData

DAHUA_ALLOWED_DETAILS = ["deviceType", "serialNumber"]

class DahuaVTOClient(asyncio.Protocol):
    def __init__(self, host, username, password, message_callback):
        self.dahua_details = {}
        self.host = host
        self.username = username
        self.password = password
        self._message_callback = message_callback

        self.realm = None
        self.random = None
        self.request_id = 1
        self.session_id = 0
        self.keep_alive_interval = 0
        self.transport = None

        self._loop = asyncio.get_event_loop()

    def connection_made(self, transport):
        logging.debug("Connection established")

        try:
            self.transport = transport

            self.load_dahua_info()
            self.pre_login()

        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logging.error("Failed to handle message, error: {}, Line: {}".format(ex, exc_tb.tb_lineno))

    def data_received(self, data):
        try:
            message = self.parse_response(data)
            logging.debug("Data received: {}".format(message))

            message_id = message.get("id")
            params = message.get("params")

            if message_id == 1:
                error = message.get("error")

                if error is not None:
                    self.handle_login_error(error, message, params)

            elif message_id == 2:
                self.handle_login(params)

            else:
                method = message.get("method")

                if method == "client.notifyEventStream":
                    self.handle_notify_event_stream(params)

        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logging.error("Failed to handle message, error: {}, Line: {}".format(ex, exc_tb.tb_lineno))

    def handle_notify_event_stream(self, params):
        try:
            event_list = params.get("eventList")

            for message in event_list:
                code = message.get("Code")

                for k in self.dahua_details:
                    if k in DAHUA_ALLOWED_DETAILS:
                        message[k] = self.dahua_details.get(k)

                self._message_callback(message)

        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logging.error("Failed to handle event, error: {}, Line: {}".format(ex, exc_tb.tb_lineno))

    def handle_login_error(self, error, message, params):
        error_message = error.get("message")

        if error_message == "Component error: login challenge!":
            self.random = params.get("random")
            self.realm = params.get("realm")
            self.session_id = message.get("session")

            self.login()

    def handle_login(self, params):
        keep_alive_interval = params.get("keepAliveInterval")

        if keep_alive_interval is not None:
            self.keep_alive_interval = params.get("keepAliveInterval") - 5

            Timer(self.keep_alive_interval, self.keep_alive).start()

            self.attach_event_manager()

    def eof_received(self):
        logging.info('Server sent EOF message')

        self._loop.stop()

    def connection_lost(self, exc):
        logging.error('server closed the connection')

        self._loop.stop()

    def send(self, message_data: MessageData):
        self.request_id += 1

        message_data.id = self.request_id

        if not self.transport.is_closing():
            self.transport.write(message_data.to_message())

    def pre_login(self):
        logging.debug("Prepare pre-login message")

        message_data = MessageData(self.request_id, self.session_id)
        message_data.login(self.username)

        if not self.transport.is_closing():
            self.transport.write(message_data.to_message())

    def login(self):
        logging.debug("Prepare login message")

        password = self._get_hashed_password(self.random, self.realm, self.username, self.password)

        message_data = MessageData(self.request_id, self.session_id)
        message_data.login(self.username, password)

        self.send(message_data)

    def attach_event_manager(self):
        logging.info("Attach event manager")

        message_data = MessageData(self.request_id, self.session_id)
        message_data.attach()

        self.send(message_data)

    def keep_alive(self):
        logging.debug("Keep alive")

        message_data = MessageData(self.request_id, self.session_id)
        message_data.keep_alive(self.keep_alive_interval)

        self.send(message_data)

        Timer(self.keep_alive_interval, self.keep_alive).start()

    def load_dahua_info(self):
        try:
            logging.debug("Loading Dahua details")

            url = "http://{}/cgi-bin/magicBox.cgi?action=getSystemInfo".format(self.host)

            response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password))

            response.raise_for_status()

            lines = response.text.split("\r\n")

            for line in lines:
                if "=" in line:
                    parts = line.split("=")
                    self.dahua_details[parts[0]] = parts[1]

        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logging.error("Failed to retrieve Dahua model, error: {}, Line: {}".format(ex, exc_tb.tb_lineno))

    @staticmethod
    def parse_response(response):
        result = None

        try:
            response_parts = str(response).split("\\n")
            for response_part in response_parts:
                start = None
                if '{"' in response_part:
                    start = response_part.index('{"')
                elif '{ "' in response_part:
                    start = response_part.index('{ "')
                elif '{' in response_part:
                    start = response_part.index('{')
                
                if start is not None:
                    message = response_part[start:]

                    result = json.loads(message)

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logging.error("Failed to read data: {}, error: {}, Line: {}".format(response, e, exc_tb.tb_lineno))

        return result

    @staticmethod
    def _get_hashed_password(random, realm, username, password):
        password_str = "{}:{}:{}".format(username, realm, password)
        password_bytes = password_str.encode('utf-8')
        password_hash = hashlib.md5(password_bytes).hexdigest().upper()

        random_str = "{}:{}:{}".format(username, random, password_hash)
        random_bytes = random_str.encode('utf-8')
        random_hash = hashlib.md5(random_bytes).hexdigest().upper()

        return random_hash
