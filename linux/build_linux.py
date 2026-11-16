#!/usr/bin/env python3
"""Package OpenInk Linux and pinned assets without private captures or data."""
import hashlib
import io
import json
from pathlib import Path
import tarfile


def main():
    root=Path(__file__).resolve().parents[1]
    destination=root/"linux/dist"
    destination.mkdir(exist_ok=True)
    files=sorted(p for p in (root/"commun/inkora").rglob('*') if p.is_file()and'__pycache__'not in p.parts and p.suffix!='.pyc')
    files += [*sorted(root.glob("README*.md")),root/'THIRD_PARTY_NOTICES.md',root/'CONTRIBUTING.md']
    files += sorted(p for p in (root/'docs').rglob('*') if p.is_file())
    files += [root/"linux"/name for name in ("inkora_linux.py","openink_linux.py","Lancer-Inkora.sh","Lancer-OpenInk.sh","installer_raccourci.py","openink.svg","build_deb.py","build_linux.py","build_brand_assets.py")]
    files += sorted(p for p in (root/'linux/tests').rglob('*') if p.is_file()and'__pycache__'not in p.parts and p.suffix!='.pyc')
    manifest={"application":"OpenInk","version":"1.7.0","platform":"Ubuntu",
              "requires":"Python >= 3.10, Tkinter, PyGObject, GLib, libusb, systemd and CUPS client",
              "sha256":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    target=destination/"OpenInk-Ubuntu-1.7.0-sources.tar.gz"
    with tarfile.open(target,"w:gz") as archive:
        for p in files:
            archive.add(p,arcname="OpenInk/"+str(p.relative_to(root)))
        data=(json.dumps(manifest,indent=2)+"\n").encode()
        info=tarfile.TarInfo("OpenInk/BUILD_INFO.json")
        info.size=len(data)
        info.mode=0o644
        archive.addfile(info,io.BytesIO(data))
    print(target)
    print("SHA-256",hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=="__main__":main()
