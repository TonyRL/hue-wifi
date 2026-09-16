# Builds opkg, wpa_supplicant and dropbear for the Philips Hue Bridge 2.x (OpenWrt 19.07.8, mips_24kc, musl). The bridge target "bsb002/generic" has no public SDK; ath79/generic 19.07.8 has the same arch and libc.
FROM ubuntu:20.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl file gawk gettext git libncurses5-dev libssl-dev \
    python2 python3 python3-distutils rsync unzip wget xz-utils zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m build
USER build
WORKDIR /home/build
ARG SDK=openwrt-sdk-19.07.8-ath79-generic_gcc-7.5.0_musl.Linux-x86_64
RUN curl -sSL https://downloads.openwrt.org/releases/19.07.8/targets/ath79/generic/$SDK.tar.xz | tar xJ && mv $SDK sdk
WORKDIR /home/build/sdk
RUN ./scripts/feeds update base && ./scripts/feeds install opkg wpa-supplicant kmod-cfg80211
# kmod-cfg80211 is not built; setting it only turns on the nl80211 driver in wpa_supplicant.
# dropbear from OpenWrt main (2026.94): the 19.07 feed has 2019.78 built without ECDSA/Ed25519. 19.07 kconfig lacks "imply"; its autoconf regenerates configure without the src/ aux-dir, so copy the helpers.
ARG OPENWRT_MAIN=190a24c7cd93c3b9e9beca6067c02fe3f7613d2a
RUN curl -sSL https://codeload.github.com/openwrt/openwrt/tar.gz/$OPENWRT_MAIN \
    | tar xz -C package --strip-components=4 --wildcards '*/package/network/services/dropbear/*' \
    && sed -i '/^\s*imply /d' package/dropbear/Config.in
RUN printf 'CONFIG_PACKAGE_opkg=y\nCONFIG_PACKAGE_wpa-supplicant=y\nCONFIG_PACKAGE_kmod-cfg80211=m\nCONFIG_PACKAGE_dropbear=y\n' > .config && make defconfig
RUN make package/dropbear/prepare \
    && cp scripts/config.sub scripts/config.guess build_dir/target-*/dropbear-*/src/install-sh build_dir/target-*/dropbear-*/ \
    && make package/opkg/compile package/hostapd/compile package/dropbear/compile -j"$(nproc)"

FROM scratch
ARG B=/home/build/sdk/bin/packages/mips_24kc/base
COPY --from=build $B/opkg_*.ipk $B/uclient-fetch_*.ipk $B/libuclient*.ipk $B/libubox2*.ipk \
    $B/libustream-wolfssl*.ipk $B/libwolfssl*.ipk \
    $B/wpa-supplicant_*.ipk $B/hostapd-common_*.ipk $B/libnl-tiny_*.ipk $B/libubus2*.ipk \
    /home/build/sdk/bin/targets/ath79/generic/packages/dropbear_*.ipk /
