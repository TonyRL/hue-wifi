# hue-wifi

Connect Philips Hue Bridge V2.1 to your network through Wi-Fi instead of using its Ethernet port.

Tested on firmware 1.78.1978293000 (released on Aug 27, 2026, custom-built OpenWrt 19.07.8 r11364, kernel 4.14.241, `bsb002/generic`, `mips_24kc`, Bridge 2.1 with QCA9533 SoC).

This also builds and installs `opkg`, `wpa_supplicant`, a current `dropbear`, and the ath9k Wi-Fi kernel modules for a rooted Philips Hue Bridge 2.x.

## Prerequisites

- A rooted bridge with a root shell on the serial console, following [Michal's guide](https://wejn.org/2024/11/rooting-hue-bridge-with-firmware-1967054020/).
- A PC on the same LAN with Docker and python3.

## What is in the repository

| File | Output | Estimated Build time on GitHub Actions |
|---|---|---|
| `Dockerfile` | `opkg`, `uclient-fetch`, `wpa-supplicant`, `hostapd-common`, `libnl-tiny`, `libubus`, `libubox`, `libustream-wolfssl`, `libwolfssl`, `dropbear` | about 15 minutes |
| `Dockerfile.kmods` | `kmod-cfg80211`, `kmod-mac80211`, `kmod-ath`, `kmod-ath9k-common`, `kmod-ath9k`, `iw`, `wireless-regdb` | about 30 minutes |
| `.github/workflows/build.yml` | Runs both Dockerfiles and uploads the `ipk` and `kmods` artifacts | |

`Dockerfile` uses the official OpenWrt 19.07.8 SDK for `ath79/generic`. The bridge target has no public SDK, but the architecture and libc are the same, and the resulting packages are ABI-compatible. The `dropbear` package comes from OpenWrt main because the 19.07 build of 2019.78 has ECDSA and Ed25519 disabled.

`Dockerfile.kmods` runs the full OpenWrt 19.07.8 buildroot for `ar71xx`. Kernel modules must match the kernel exactly, and Signify's kernel differs from stock 19.07.8 in four config options. The stock modules crash the module loader. The file header lists the differences and how they were found.

## Building

GitHub Actions: push, or run the `build` workflow by hand, then download the `ipk` and `kmods` artifacts.

Locally:

```
docker build --output out .
docker build -f Dockerfile.kmods --output out-kmods .
```

The kmods build needs about 10 GB of disk.

## Getting files onto the bridge

The bridge has `curl` but no `wget`. `tools/serve.py` serves the current directory and also accepts uploads from the bridge:

```
mkdir -p /tmp/km && cp out/*.ipk out-kmods/*.ipk /tmp/km/
cd /tmp/km && python3 ~/hue-wifi/tools/serve.py 8000
```

On the bridge, download with `curl -sf http://<pc-ip>:8000/<file> > <file>` and upload with `curl -T <file> http://<pc-ip>:8000/<file>`.

## Installing

`opkg` is not on the bridge, so bootstrap by extracting the packages by hand. Every `.ipk` is a tar archive holding `data.tar.gz`:

```
cd /tmp
for f in *.ipk; do tar xzOf $f ./data.tar.gz | tar xz -C /; done
```

Notes:

- Do not extract `libubox` or `libubus` if `/lib/libubox.so` and `/lib/libubus.so.20210603` already exist. Firmware 1.78 has both.
- `dropbear` registers `scp`, `ssh` and `ssh-keygen` as opkg alternatives. After a hand extraction, add `ln -s ../sbin/dropbear /usr/bin/scp`.
- The kmod packages install `/etc/modules.d/ath9k`, so the modules load at every boot. Everything lives in the overlay, and a factory reset removes it all.

After extracting the kernel modules, reboot. Then check:

```
dmesg | grep -E 'ath:|ieee80211'
ls /sys/class/ieee80211/
```

A `phy0` entry and an `Atheros AR9531` line mean the radio is up.

## Restoring opkg

Signify removed `opkg` but left its package database, its keys and a feed list that points at a `bsb002` target directory which does not exist on downloads.openwrt.org. The `ipk` artifact holds everything needed, plus `openwrt-keyring` from the 19.07.8 feed for signature checks. `tools/distfeeds.conf` lists the 19.07.8 `mips_24kc` package feeds and leaves out the target feed on purpose, because that feed carries ath79 kernel modules that must never be installed on this bridge.

```
cd /tmp
for f in opkg_*.ipk uclient-fetch*.ipk libuclient*.ipk libustream*.ipk libwolfssl*.ipk openwrt-keyring*.ipk; do tar xzOf $f ./data.tar.gz | tar xz -C /; done
mv /etc/opkg/distfeeds.conf /etc/opkg/distfeeds.conf.signify
cp /tmp/distfeeds.conf /etc/opkg/distfeeds.conf
ln -s /bin/uclient-fetch /usr/bin/wget
opkg update
opkg install htop
```

The `wget` link is required. opkg downloads by calling `wget`, the firmware has none, and a hand extraction skips the opkg alternative that `uclient-fetch` normally registers. Without it every download fails with `wget returned 255`.

## Upgrading dropbear

Signify ships dropbear 2019.78 built without ECDSA and Ed25519, so only `ssh-rsa` client keys work. The `ipk` artifact has dropbear 2026.94 with both. Install it through opkg, after backing up the files Signify customised:

```
cp /usr/sbin/dropbear /root/dropbear.2019
cp /etc/init.d/dropbear /root/dropbear.init.signify
cp /etc/config/dropbear /root/dropbear.config.signify
opkg install /tmp/dropbear_2026.94-2_mips_24kc.ipk
cp /root/dropbear.init.signify /etc/init.d/dropbear
/etc/init.d/dropbear restart
ps | grep dropbea[r]
```

Keep Signify's init script. The packaged one calls `extra_command`, which `/etc/rc.common` on 19.07 does not have, so it aborts on every `start` and `stop`. Signify's script only passes long-standing command-line options and drives the new binary without change. opkg keeps the existing `/etc/config/dropbear` and places the packaged one at `/etc/config/dropbear-opkg`. It may also delete the RSA host key it considers obsolete; the init script generates a new one on the next start, and clients then warn about a changed host key once.

Test from the PC with a non-RSA key:

```
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 root@<bridge> 'dropbear -V 2>&1 | head -1'
```

## Wi-Fi configuration

Signify ships `/etc/config/wireless` with the right radio path and the radio disabled. Enable it as a client on a test interface first:

```
uci set wireless.radio0.disabled=0
uci set wireless.@wifi-iface[0].mode=sta
uci set wireless.@wifi-iface[0].network=wwan
uci set wireless.@wifi-iface[0].ssid='YOUR_SSID'
uci set wireless.@wifi-iface[0].encryption=psk2
uci set wireless.@wifi-iface[0].key='YOUR_PASSWORD'
uci set network.wwan=interface
uci set network.wwan.proto=dhcp
uci commit wireless; uci commit network
reboot
```

`uci commit` without a package name fails on this firmware. Verify with `iw dev wlan0 link` and `ifstatus wwan`.

The radio supports HT40, which can be switched using:

```
uci set wireless.radio0.htmode=HT40
uci commit wireless
wifi
```

To make Wi-Fi the bridge's main network, Signify's services use the interface named `lan`:

```
uci set wireless.@wifi-iface[0].network=lan
uci delete network.lan.ifname
uci delete network.wwan
uci commit wireless; uci commit network
reboot
```

The HomeKit mDNS service binds to the Ethernet port by name. Point it at `wlan0` as described in [R. X. Seger's guide](https://medium.com/@rxseger/enabling-the-hidden-wi-fi-radio-on-the-philips-hue-bridge-2-0-42949f0154e1#486e):

```
grep -l eth1 /etc/config/*
sed -i "s/option netif 'eth1'/option netif 'wlan0'/" /etc/config/hk_mdns
/etc/init.d/hap restart; /etc/init.d/mdnsd restart
```

The `grep` shows every config file that still names the port. On firmware 1.78 `hk_hap` has no interface setting and needs no change. The guide reports that HomeKit stopped working after this change on an older firmware, so test the Hue app and HomeKit before removing the cable for good.

To go back to the cable, run this on the serial console:

```
uci set network.lan.ifname=eth1
uci set wireless.radio0.disabled=1
uci commit wireless; uci commit network
reboot
```

This keeps the modules and the Wi-Fi credentials in place. Set `wireless.radio0.disabled=0` and `network.lan.ifname` back as above to switch again. To remove everything and return to the stock state, do a factory reset with the button. It wipes the overlay, including the modules, `wpa_supplicant` and `dropbear`.

## Why the stock kernel modules do not work

The kernel is stock 4.14.241 from OpenWrt 19.07.8 with the legacy `ar71xx` board layout (`board=BSB002`, no device tree). The Wi-Fi platform device is named `qca953x_wmac`, which the stock ath9k driver matches. But the kernel was built with a different config, which changes structure layouts:

| Option | Signify | Stock | How it showed up |
|---|---|---|---|
| `KALLSYMS` | on | off | oops printed symbol names; `struct module` 352 bytes instead of 320 |
| `PCI` | off | on | no `pci_*` functions in `/proc/kallsyms` |
| `HARDENED_USERCOPY` | off | on | no `__check_object_size` in `/proc/kallsyms` |
| `NETFILTER_INGRESS` | off | on | `struct net_device` reference count at offset 712, not 716, read by disassembling `netdev_refcnt_read` in the kernel binary from `/dev/mtd6` |
| compiler | GCC 8.3.0 | GCC 7.5.0 | first line of `dmesg` |

`Dockerfile.kmods` applies all of these. Before loading the modules on another firmware, run the same checks with `tools/check-kernel.py`. Collect on the bridge and upload with `curl -T`:

```
cat /proc/kallsyms > /tmp/kallsyms
cat /proc/cmdline            # ubi.mtd=7 means bank 1, kernel-1 on mtd6; otherwise mtd4
cat /dev/mtd6 > /tmp/kernel.bin
```

Then on the PC:

```
python3 tools/check-kernel.py --kallsyms kallsyms --module zram.ko --kernel kernel.bin --ipks out-kmods
```

It reports the `struct module` size, every function the modules import that the kernel does not export, and the `struct net_device` reference count offset, each as OK or MISMATCH. A mismatch means another kernel option differs and the module would oops the kernel. Only `uname -r` equal to 4.14.241 is safe to try at all.

The bridge has two firmware banks. The running one is the bank named by `ubi.mtd=` on the kernel command line. `mtd4` is `kernel-0`, `mtd6` is `kernel-1`.

## GPL source

- [hauke/philips-hue-bsb002](https://github.com/hauke/philips-hue-bsb002) (version 1811120916) 
- [rettichschnidi/bsb002-legal-sources](https://github.com/rettichschnidi/bsb002-legal-sources) (version 1802201122) 

Or request one from [open.source.lighting@signify.com](https://web.archive.org/web/20210123112642/https://community.hueessentials.com/t/cannot-add-hue-bridge-to-hue-essentials-wrong-ip-address/577). The offer is valid for three years after the software update.
