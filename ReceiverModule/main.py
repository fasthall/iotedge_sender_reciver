# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import json
import os
import random
import time
import sys
import iothub_client
from iothub_client import IoTHubClient, IoTHubClientError, IoTHubTransportProvider
from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError
import pymssql

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# String containing Hostname, Device Id & Device Key & Module Id in the format:
# "HostName=<host_name>;DeviceId=<device_id>;SharedAccessKey=<device_key>;ModuleId=<module_id>;GatewayHostName=<gateway>"
CONNECTION_STRING = "[Device Connection String]"

# Callback received when the message that we're forwarding is processed.
def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "Confirmation[%d] received for message with result = %s" % (user_context, result) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    SEND_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_CALLBACKS )

# receive_message_callback is invoked when an incoming message arrives on the specified 
# input queue (in the case of this sample, "input1").  Because this is a filter module, 
# we will forward this message onto the "output1" queue.
def receive_message_callback(message, hubManager):
    global RECEIVE_CALLBACKS
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    message_text = message_buffer[:size].decode('utf-8')
    data = json.loads(message_text)
    data['receiver'] = int(time.time() * 1000)
    print("Received: {0}".format(data))
    hubManager.store_to_db(data['sender'], data['receiver'])
    return IoTHubMessageDispositionResult.ACCEPTED


class HubManager(object):

    def __init__(
            self,
            connection_string):
        self.client_protocol = PROTOCOL
        self.client = IoTHubClient(connection_string, PROTOCOL)
        self.conn = pymssql.connect('sql:1433', 'SA', 'Strong!Passw0rd', "MeasurementsDB")
        self.cursor = self.conn.cursor()

        # set the time until a message times out
        self.client.set_option("messageTimeout", MESSAGE_TIMEOUT)
        # some embedded platforms need certificate information
        self.set_certificates()
        
        # sets the callback when a message arrives on "input1" queue.  Messages sent to 
        # other inputs or to the default will be silently discarded.
        self.client.set_message_callback("input1", receive_message_callback, self)

    def set_certificates(self):
        isWindows = sys.platform.lower() in ['windows', 'win32']
        if not isWindows:
            CERT_FILE = os.environ['EdgeModuleCACertificateFile']        
            print("Adding TrustedCerts from: {0}".format(CERT_FILE))
            
            # this brings in x509 privateKey and certificate
            file = open(CERT_FILE)
            try:
                self.client.set_option("TrustedCerts", file.read())
                print ( "set_option TrustedCerts successful" )
            except IoTHubClientError as iothub_client_error:
                print ( "set_option TrustedCerts failed (%s)" % iothub_client_error )

            file.close()

    # Forwards the message received onto the next stage in the process.
    def forward_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(
            outputQueueName, event, send_confirmation_callback, send_context)

    def store_to_db(self, sender, receiver):
        self.cursor.execute('INSERT INTO MeasurementsDB.dbo.test (Sender, Receiver) Values ({0}, {1});'.format(sender, receiver))
        self.conn.commit()
        ts = int(time.time() * 1000)
        self.cursor.execute('INSERT INTO MeasurementsDB.dbo.result (Sender, Receiver, DB) Values ({0}, {1}, {2});'.format(sender, receiver, ts))

def main(connection_string):
    try:
        print ( "\nPython %s\n" % sys.version )
        print ( "IoT Hub Client for Python" )

        hub_manager = HubManager(connection_string)

        print ( "Starting the IoT Hub Python sample using protocol %s..." % hub_manager.client_protocol )
        print ( "The sample is now waiting for messages and will indefinitely.  Press Ctrl-C to exit. ")

        while True:
            time.sleep(1000)

    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubClient sample stopped" )

if __name__ == '__main__':
    try:
        CONNECTION_STRING = os.environ['EdgeHubConnectionString']

    except Exception as error:
        print ( error )
        sys.exit(1)

    main(CONNECTION_STRING)