#!/bin/bash

set -e

rm /etc/resolv.conf
echo nameserver 8.8.8.8 >/etc/resolv.conf
chmod 777 /tmp

cp config/mac80211_hwsim.conf /etc/modprobe.d/mac80211_hwsim.conf
cp config/99-virtual-wifi.yaml /etc/netplan/99-virtual-wifi.yaml
chmod -R 700 /etc/netplan
netplan apply

apt update
DEBIAN_FRONTEND=noninteractive apt install -y apt-utils
DEBIAN_FRONTEND=noninteractive apt install -y \
  dnsmasq \
  hostapd \
  wpasupplicant \
  iw \
  libdw1 \
  rfkill

apt remove -y \
  snapd \
  systemd-timesyncd

mkdir -p /etc/hostapd
mkdir -p /etc/systemd/system/bluetooth.service.d
mkdir -p /etc/systemd/system/wpa_supplicant.service.d
mkdir -p /etc/systemd/system/dnsmasq.service.d
mkdir -p /etc/systemd/system/hostapd.service.d
mkdir -p /etc/wpa_supplicant

cp config/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf

sed -ie 's+ExecStart.*+ExecStart=/sbin/wpa_supplicant -u -s -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf+' /etc/systemd/system/dbus-fi.w1.wpa_supplicant1.service

cp config/dnsmasq.conf /etc/dnsmasq.conf
cp config/hostapd.conf /etc/hostapd/hostapd.conf
cp config/bluez.conf /etc/systemd/system/bluetooth.service.d/override.conf
cp config/hostapd.service /etc/systemd/system/hostapd.service.d/override.conf
cp config/dnsmasq.service /etc/systemd/system/dnsmasq.service.d/override.conf
cp config/wifi_master.service /etc/systemd/system/wifi_master.service

systemctl daemon-reload
systemctl unmask wifi_master hostapd dnsmasq wpa_supplicant
systemctl enable --now wifi_master hostapd dnsmasq
systemctl restart wifi_master hostapd dnsmasq wpa_supplicant
