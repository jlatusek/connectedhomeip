ARG VERSION=latest
FROM ghcr.io/project-chip/chip-build:${VERSION}
LABEL org.opencontainers.image.source https://github.com/project-chip/connectedhomeip

USER root


RUN set -x \
	&& apt-get update \
	&& DEBIAN_FRONTEND=noninteractive apt-get install -fy --no-install-recommends \
	qemu \
	git \
	fakeroot \
	build-essential \
	ncurses-dev \
	xz-utils \
	libssl-dev \
	bc flex \
	libelf-dev \
	bison \
	make \
	&& apt-get clean \
	&& rm -rf /var/lib/apt/lists/ \
	&& : # last line

RUN set -x 
# Download Linux kernel source
RUN echo ""	&& mkdir -p /tmp/workdir && cd /tmp/workdir 
WORKDIR /tmp/workdir
RUN echo ""	&& curl https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.7.1.tar.xz -o linux-6.7.1.tar.xz 
RUN echo ""	&& tar -xJf linux-6.7.1.tar.xz 
RUN echo ""	&& cd linux-6.7.1 
# Set configuration for btvirt
WORKDIR /tmp/workdir/linux-6.7.1
RUN make x86_64_defconfig 
RUN ./scripts/config -e MAC80211 
RUN ./scripts/config -e MAC80211_HWSIM 
RUN ./scripts/config -e BT 
RUN ./scripts/config -e BT_BREDR 
RUN ./scripts/config -e BT_HCIVHCI 
# Compile
RUN echo ""	&& export MAKEFLAGS=-j$(nproc) \
	&& make olddefconfig  \
	&& make
RUN make modules_install INSTALL_MOD_PATH=/opt/ubuntu-qemu/rootfs \
	&& cp arch/x86/boot/bzImage /opt/ubuntu-qemu/bzImage
# Download Ubuntu image for QEMU
RUN echo ""	&& mkdir -p /opt/ubuntu-qemu 
RUN echo ""	&& curl https://cloud-images.ubuntu.com/minimal/releases/jammy/release/ubuntu-22.04-minimal-cloudimg-amd64.img \
	-o /opt/ubuntu-qemu/ubuntu-22.04-minimal-cloudimg-amd64.img 
RUN echo ""	&& curl https://cloud-images.ubuntu.com/minimal/releases/jammy/release/SHA256SUMS \
	-o /opt/ubuntu-qemu/SHA256SUMS 
RUN echo ""	&& cd /opt/ubuntu-qemu 
WORKDIR /opt/ubuntu-qemu
# RUN echo ""	&& sha256sum -c SHA256SUMS 2>&1 | grep OK 
# RUN echo ""	&& : # last line


USER $USER_NAME
WORKDIR $USER_HOME
