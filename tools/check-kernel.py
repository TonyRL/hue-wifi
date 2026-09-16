#!/usr/bin/env python3
"""Compare a Hue Bridge kernel against the kmods built by Dockerfile.kmods.

Collect on the bridge (see README) and pass:
  --kallsyms  /proc/kallsyms copied from the bridge
  --module    any stock module from the bridge, e.g. /lib/modules/<ver>/zram.ko
  --kernel    dump of the running kernel partition (cat /dev/mtdN > kernel.bin)
  --ipks      directory with the built kmod-*.ipk files (out-kmods)
Needs readelf (any binutils) and python3. No MIPS toolchain required.
"""
import argparse, glob, lzma, os, re, struct, subprocess, tarfile, tempfile, io

def readelf(*a): return subprocess.run(["readelf", "-W", *a], capture_output=True, text=True).stdout

def this_module_size(ko):
    m = re.search(r"\.gnu\.linkonce\.this_module\s+PROGBITS\s+\S+\s+\S+\s+([0-9a-f]+)", readelf("-S", ko))
    return int(m.group(1), 16) if m else None

def extract_ipks(d, dest):
    kos = []
    for ipk in glob.glob(os.path.join(d, "kmod-*.ipk")):
        with tarfile.open(ipk) as outer:
            data = outer.extractfile("./data.tar.gz").read()
        with tarfile.open(fileobj=io.BytesIO(data)) as inner:
            for m in inner.getmembers():
                if m.name.endswith(".ko"):
                    p = os.path.join(dest, os.path.basename(m.name))
                    open(p, "wb").write(inner.extractfile(m).read()); kos.append(p)
    return kos

def undefined(ko): return {l.split()[-1] for l in readelf("-s", ko).splitlines() if " UND " in l and not l.rstrip().endswith("UND")}
def exported(ko): return set(re.findall(r"\]\s+(\S+)", readelf("-p", "__ksymtab_strings", ko)))

def kernel_image(path):
    d = open(path, "rb").read()
    magic, _, _, size, load = struct.unpack(">IIIII", d[:20])
    assert magic == 0x27051956, "not a uImage"
    return load, lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(d[64:64 + size])

def lw_offset(word, rs, rt):
    if word >> 26 == 0x23 and (word >> 21) & 31 == rs and (word >> 16) & 31 == rt: return word & 0xFFFF

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--kallsyms", required=True); ap.add_argument("--module", required=True)
ap.add_argument("--kernel"); ap.add_argument("--ipks", required=True)
a = ap.parse_args()
tmp = tempfile.mkdtemp(); kos = extract_ipks(a.ipks, tmp)
ours = next(k for k in kos if k.endswith("zram.ko")) if any(k.endswith("zram.ko") for k in kos) else kos[0]
print(f"struct module: bridge {this_module_size(a.module)} bytes, built {this_module_size(ours)} bytes ->",
      "OK" if this_module_size(a.module) == this_module_size(ours) else "MISMATCH (KALLSYMS or similar option differs)")

syms = [l.split() for l in open(a.kallsyms)]
funcs = {s[2] for s in syms if len(s) == 3 and s[1] in "tTwW"}
need = set().union(*(undefined(k) for k in kos)) - set().union(*(exported(k) for k in kos))
missing = sorted(need - funcs)
print(f"module imports not found as kernel functions: {len(missing)} (data symbols such as jiffies are expected here)")
print("  " + " ".join(missing))

if a.kernel:
    load, raw = kernel_image(a.kernel)
    print("kernel:", re.search(rb"Linux version [^\x00]+", raw).group(0).decode()[:120])
    addr = next(int(s[0], 16) for s in syms if s[2] == "netdev_refcnt_read")
    word = struct.unpack(">I", raw[addr - load: addr - load + 4])[0]
    theirs = lw_offset(word, 4, 2)  # lw v0,OFF(a0)
    cfg = next(k for k in kos if k.endswith("cfg80211.ko")); text = open(cfg, "rb").read()
    m = re.search(rb"\x8c\x85(..)\x8c\xa4\x00\x00\x24\x84\x00\x01\xac\xa4\x00\x00", text, re.S)  # dev_hold()
    mine = struct.unpack(">H", m.group(1))[0] if m else None
    print(f"net_device refcount offset: bridge {theirs}, built cfg80211 {mine} ->", "OK" if theirs == mine else "MISMATCH (NETFILTER_INGRESS or another net_device option differs)")
