#
#    Copyright (c) 2021 Project CHIP Authors
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#

"""
Handles linux-specific functionality for running test cases
"""

from time import sleep
import logging
import os
import subprocess
import sys
import time

from .test_definition import ApplicationPaths
import psutil

test_environ = os.environ.copy()


def EnsureNetworkNamespaceAvailability():
    if os.getuid() == 0:
        logging.debug("Current user is root")
        logging.warn("Running as root and this will change global namespaces.")
        return

    os.execvpe(
        "unshare", ["unshare", "--map-root-user", "-n", "-m", "python3",
                    sys.argv[0], '--internal-inside-unshare'] + sys.argv[1:],
        test_environ)


def EnsurePrivateState():
    logging.info("Ensuring /run is privately accessible")

    logging.debug("Making / private")
    if os.system("mount --make-private /") != 0:
        logging.error("Failed to make / private")
        logging.error("Are you using --privileged if running in docker?")
        sys.exit(1)

    logging.debug("Remounting /run")
    if os.system("mount -t tmpfs tmpfs /run") != 0:
        logging.error("Failed to mount /run as a temporary filesystem")
        logging.error("Are you using --privileged if running in docker?")
        sys.exit(1)


def CreateNamespacesForAppTest(ble_wifi: bool):
    """
    Creates appropriate namespaces for a tool and app binaries in a simulated
    isolated network.
    """
    COMMANDS = [
        # 2 virtual hosts: for app and for the tool
        "ip netns add app",
        "ip netns add tool",

        # create links for switch to net connections
        "ip link add eth-app type veth peer name eth-app-switch",
        "ip link add eth-tool type veth peer name eth-tool-switch",
        "ip link add eth-ci type veth peer name eth-ci-switch",

        # link the connections together
        "ip link set eth-app netns app",
        "ip link set eth-tool netns tool",

        "ip link add name br1 type bridge",
        "ip link set br1 up",
        "ip link set eth-app-switch master br1",
        "ip link set eth-tool-switch master br1",
        "ip link set eth-ci-switch master br1",

        # mark connections up
        "ip netns exec app ip addr add 10.10.10.1/24 dev eth-app",
        "ip netns exec app ip link set dev eth-app up",
        "ip netns exec app ip link set dev lo up",
        "ip link set dev eth-app-switch up",

        "ip netns exec tool ip addr add 10.10.10.2/24 dev eth-tool",
        "ip netns exec tool ip link set dev eth-tool up",
        "ip netns exec tool ip link set dev lo up",
        "ip link set dev eth-tool-switch up",

        # Force IPv6 to use ULAs that we control
        "ip netns exec tool ip -6 addr flush eth-tool",
        "ip netns exec app ip -6 addr flush eth-app",
        "ip netns exec tool ip -6 a add fd00:0:1:1::2/64 dev eth-tool",
        "ip netns exec app ip -6 a add fd00:0:1:1::3/64 dev eth-app",

        # create link between virtual host 'tool' and the test runner
        "ip addr add 10.10.10.5/24 dev eth-ci",
        "ip link set dev eth-ci up",
        "ip link set dev eth-ci-switch up",
    ]

    for command in COMMANDS:
        logging.debug("Executing '%s'" % command)
        if os.system(command) != 0:
            logging.error("Failed to execute '%s'" % command)
            logging.error("Are you using --privileged if running in docker?")
            sys.exit(1)

    # IPv6 does Duplicate Address Detection even though
    # we know ULAs provided are isolated. Wait for 'tenative'
    # address to be gone.

    logging.info('Waiting for IPv6 DaD to complete (no tentative addresses)')
    for i in range(100):  # wait at most 10 seconds
        output = subprocess.check_output(['ip', 'addr'])
        if b'tentative' not in output:
            logging.info('No more tentative addresses')
            break
        time.sleep(0.1)
    else:
        logging.warn("Some addresses look to still be tentative")


def RemoveNamespaceForAppTest(ble_wifi: bool = False):
    """
    Removes namespaces for a tool and app binaries previously created to simulate an
    isolated network. This tears down what was created in CreateNamespacesForAppTest.
    """
    COMMANDS = [
        "ip link set dev eth-ci down",
        "ip link set dev eth-ci-switch down",
        "ip addr del 10.10.10.5/24 dev eth-ci",

        "ip link set br1 down",
        "ip link delete br1",

        "ip link delete eth-ci-switch",
        "ip link delete eth-tool-switch",
        "ip link delete eth-app-switch",

        "ip netns del tool",
        "ip netns del app",
    ]

    for command in COMMANDS:
        logging.debug("Executing '%s'" % command)
        if os.system(command) != 0:
            breakpoint()
            logging.error("Failed to execute '%s'" % command)
            sys.exit(1)


wifi = None
ble = None


def PrepareNamespacesForTestExecution(in_unshare: bool, ble_wifi: bool):
    global wifi
    global ble

    if not in_unshare:
        EnsureNetworkNamespaceAvailability()
    elif in_unshare:
        EnsurePrivateState()

    CreateNamespacesForAppTest(ble_wifi)
    if (ble_wifi):
        wifi = VirtualWifi(
            hostapd_path='/usr/sbin/hostapd',
            dnsmasq_path='/usr/sbin/dnsmasq',
            wpa_supplicant_path='/usr/sbin/wpa_supplicant'
        )
        wifi.start()
        ble = VirtualBle(btvirt_path='/usr/bin/btvirt')
        ble.start()


def ShutdownNamespaceForTestExecution(ble_wifi: bool):
    global wifi
    global ble

    wifi.stop()
    ble.stop()
    RemoveNamespaceForAppTest(ble_wifi)


class VirtualWifi:
    def __init__(self, hostapd_path: str, dnsmasq_path: str, wpa_supplicant_path: str):
        self._hostapd_path = hostapd_path
        self._dnsmasq_path = dnsmasq_path
        self._wpa_supplicant_path = wpa_supplicant_path
        _chip_project_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        self._hostapd_conf = os.path.join(
            _chip_project_dir, "integrations/docker/images/stage-2/chip-build-linux-qemu/files/config/hostapd.conf")
        self._dnsmasq_conf = os.path.join(
            _chip_project_dir, "integrations/docker/images/stage-2/chip-build-linux-qemu/files/config/dnsmasq.conf")
        self._wpa_supplicant_conf = os.path.join(
            _chip_project_dir, "integrations/docker/images/stage-2/chip-build-linux-qemu/files/config/wpa_supplicant.conf")
        self._hostapd = None
        self._dnsmasq = None
        self._wpa_supplicant = None
        self.wlan0_phy = None
        self.wlan1_phy = None

    def _is_process_running(self, name: str) -> bool:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == name:
                return True
        return False

    def _get_phy(self, dev: str) -> str:
        output = subprocess.check_output(['iw', 'dev', dev, 'info'])
        for line in output.split(b'\n'):
            if b'wiphy' in line:
                wiphy = int(line.split(b' ')[1])
                return f"phy{wiphy}"
        raise ValueError(f'No wiphy found for {dev}')

    def _move_to_netns(self, phy: str, netns: str | int):
        if type(netns) == int:
            subprocess.check_call(["iw", "phy", phy, "set", "netns", str(netns)])
        else:
            subprocess.check_call(["iw", "phy", phy, "set", "netns", "name", netns])

    def _set_ip_to_interface(self, netns: str, dev: str, ip: str):
        subprocess.check_call(["ip", "netns", "exec", netns, "ip", "addr", "add", ip, "dev", dev])
        subprocess.check_call(["ip", "netns", "exec", netns, "ip", "link", "set", "dev", dev, "up"])

    def start(self):
        self.wlan0_phy = self._get_phy('wlan0')
        self.wlan1_phy = self._get_phy('wlan1')
        self._move_to_netns(self.wlan0_phy, 'app')
        self._move_to_netns(self.wlan1_phy, 'tool')
        self._set_ip_to_interface('tool', 'wlan1', '192.168.200.1/24')

        if not self._is_process_running('hostapd'):
            self._hostapd = subprocess.Popen(["ip", "netns", "exec", "tool", self._hostapd_path, self._hostapd_conf])
        if not self._is_process_running('dnsmasq'):
            self._dnsmasq = subprocess.Popen(["ip", "netns", "exec", "tool", self._dnsmasq_path, '-d', '-C', self._dnsmasq_conf])
        if not self._is_process_running('wpa_supplicant'):
            print("wpa")
            self._wpa_supplicant = subprocess.Popen(
                ["ip", "netns", "exec", "app", self._wpa_supplicant_path, "-u", '-s', '-c', self._wpa_supplicant_conf])

    def _disable_netns(self):
        COMMANDS = [
            f"ip netns exec app iw phy {self.wlan0_phy} set netns 1",
            f"ip netns exec tool iw phy {self.wlan1_phy} set netns 1",
            "ip netns del app",
            "ip netns del tool",
        ]

        for command in COMMANDS:
            logging.debug("Executing '%s'" % command)
            if os.system(command) != 0:
                breakpoint()
                logging.error("Failed to execute '%s'" % command)
                sys.exit(1)

    def stop(self):
        if self._hostapd:
            self._hostapd.terminate()
            self._hostapd.wait()
        if self._dnsmasq:
            self._dnsmasq.terminate()
            self._dnsmasq.wait()
        if self._wpa_supplicant:
            self._wpa_supplicant.terminate()
            self._wpa_supplicant.wait()


class VirtualBle:
    def __init__(self, btvirt_path: str):
        self._btvirt_path = btvirt_path
        self._btvirt = None
        self.bluetoothctl = None

    def bletoothctl_cmd(self, cmd):
        self.bluetoothctl.stdin.write(cmd)
        self.bluetoothctl.stdin.flush()
        sleep(0.1)

    def _run_bluetoothctl(self):
        self.bluetoothctl = subprocess.Popen(["/usr/bin/bluetoothctl"], text=True,
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        sleep(3)
        self.bletoothctl_cmd("select 00:AA:01:00:00:00\n")
        self.bletoothctl_cmd("power on\n")
        self.bletoothctl_cmd("select 00:AA:01:01:00:01\n")
        self.bletoothctl_cmd("power on\n")
        self.bletoothctl_cmd("quit\n")
        (stdout_data, stderr_data) = self.bluetoothctl.communicate()
        print(stdout_data)
        print(stderr_data)
        sleep(0.5)
        self.bluetoothctl.terminate()
        self.bluetoothctl.wait()

    def start(self):
        self._btvirt = subprocess.Popen([self._btvirt_path, '-l2'])
        sleep(5)
        self._run_bluetoothctl()
        sleep(3)

    def stop(self):
        if self._btvirt:
            self._btvirt.terminate()
            self._btvirt.wait()


def PathsWithNetworkNamespaces(paths: ApplicationPaths) -> ApplicationPaths:
    """
    Returns a copy of paths with updated command arrays to invoke the
    commands in an appropriate network namespace.
    """
    return ApplicationPaths(
        chip_tool='ip netns exec tool'.split() + paths.chip_tool,
        all_clusters_app='ip netns exec app'.split() + paths.all_clusters_app,
        lock_app='ip netns exec app'.split() + paths.lock_app,
        ota_provider_app='ip netns exec app'.split() + paths.ota_provider_app,
        ota_requestor_app='ip netns exec app'.split() + paths.ota_requestor_app,
        tv_app='ip netns exec app'.split() + paths.tv_app,
        lit_icd_app='ip netns exec app'.split() + paths.lit_icd_app,
        bridge_app='ip netns exec app'.split() + paths.bridge_app,
        chip_repl_yaml_tester_cmd='ip netns exec tool'.split() + paths.chip_repl_yaml_tester_cmd,
        chip_tool_with_python_cmd='ip netns exec tool'.split() + paths.chip_tool_with_python_cmd,
    )
