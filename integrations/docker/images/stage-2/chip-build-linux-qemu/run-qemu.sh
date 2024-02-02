#!/bin/bash

IMG="/opt/ubuntu-qemu/ubuntu-22.04-minimal-cloudimg-amd64.img"
KERNEL="/opt/ubuntu-qemu/bzImage"

qemu-system-x86_64 \
	-machine ubuntu \
	-smp 2 \
	-m 512 \
	-nographic \
	-device virtio-blk-pci,drive=virtio-blk1 \
	-drive file=$IMG,id=virtio-blk1,if=none,format=qcow2,readonly=off \
	-kernel $KERNEL \
	-append 'console=ttyS0 mac80211_hwsim.radios=2 root=/dev/vda1' \
	-netdev user,id=network0,hostfwd=tcp::2222-:22 \
	-device e1000,netdev=network0,mac=52:54:00:12:34:56


	# --enable-kvm \
	# --cpu host \
