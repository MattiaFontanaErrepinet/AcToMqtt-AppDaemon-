import appdaemon.plugins.hass.hassapi as hass
import broadlink_ac_mqtt.classes.broadlink.ac_db as broadlink
import paho.mqtt.client as mqtt
import time
import json

class AcToMqtt(hass.Hass):
    def initialize(self):
        self.config = self.args.get("config")
        self.device_objects = {}
        self.previous_status = {}
        self.last_update = {}
        self.setup_mqtt()
        self.discover_devices()
        self.listen_event(self.on_mqtt_message, "mqtt_message")

    def setup_mqtt(self):
        self._mqtt = mqtt.Client(client_id=self.config["mqtt_client_id"], clean_session=True, userdata=None)

        if self.config["mqtt_user"] and self.config["mqtt_password"]:
            self._mqtt.username_pw_set(self.config["mqtt_user"], self.config["mqtt_password"])

        self._mqtt.will_set(self.config["mqtt_topic_prefix"] + "LWT", "offline", True)

        self._mqtt.on_connect = self.on_mqtt_connect

        self._mqtt.connect(self.config["mqtt_host"], port=self.config["mqtt_port"], keepalive=60, bind_address="")
        self._mqtt.loop_start()

    def on_mqtt_connect(self, client, userdata, flags, rc):
        sub_topic = self.config["mqtt_topic_prefix"] + "+/+/set"
        self._mqtt.subscribe(sub_topic)
        self.log("Listening on {} for messages".format(sub_topic))
        self._publish(self.config["mqtt_topic_prefix"] + "LWT", "online", retain=True)

    def discover_devices(self):
        discovered_devices = broadlink.discover(timeout=5, bind_to_ip=self.config["bind_to_ip"])
        devices = {}

        if discovered_devices is None:
            self.error("No Devices Found, make sure you are on the same network segment")
            return

        for device in discovered_devices:
            if device.devtype == 0x4E2a:
                devices[device.status["macaddress"]] = device

        self.device_objects = self.make_device_objects(devices)

    def make_device_objects(self, device_list=None):
        device_objects = {}

        if device_list is None or device_list == {}:
            self.error("Cannot make device objects, empty list given")
            return

        for device in device_list.values():
            device_objects[device.status["macaddress"]] = broadlink.gendevice(
                devtype=0x4E2a,
                host=(device["ip"], device["port"]),
                mac=bytearray.fromhex(device["mac"]),
                name=device["name"],
                update_interval=self.config["update_interval"]
            )

        return device_objects

    def on_mqtt_message(self, event_name, data, kwargs):
        topic = data["topic"]
        payload = json.loads(data["payload"])
        address = topic.split("/")[-2]
        function = topic.split("/")[-3]

        if address not in self.device_objects:
            self.log("Device {} not found in the list of devices".format(address))
            return

        device = self.device_objects[address]

        if function == "temp":
            device.set_temperature(float(payload))
        elif function == "power":
            if payload.lower() == "on":
                device.switch_on()
            elif payload.lower() == "off":
                device.switch_off()
        elif function == "mode":
            device.set_mode(payload)
        elif function == "fanspeed" or function == "fanspeed_homeassistant":
            device.set_fanspeed(payload)
        elif function == "mode_homeassistant":
            device.set_homeassistant_mode(payload)

    def _publish(self, topic, payload, retain=False, qos=0):
        self.log('Publishing on topic "{}", data "{}"'.format(topic, payload))
        result = self._mqtt.publish(topic, payload=payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            self.log('Publishing Result: "{}"'.format(mqtt.error_string(result.rc)))

    def publish_mqtt_info(self, status, force_update=False):
        # Publishing logic for MQTT info
        pass  # Implement according to your needs

    def stop(self):
        self._mqtt.disconnect()

