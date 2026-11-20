"""USB transport for the single pinned IU05P2 V2 operation.

Uses the locally recorded normal-mode protocol. No arbitrary images, memory
writes, cartridge EEPROM writes, recovery-mode updates or warning prototype.
"""
import hashlib
import os
import sys
import struct
import subprocess
import time
from pathlib import Path

from .printer import parse_status
from .firmware import PAYLOAD_SIZE,V2_SHA
from .usb_session import EpsonUsbPrinter,wait_packet

FLASH_BASE=0x20000000
FLASH_SIZE=0x1000000
MAIN_OFFSET=0x30000
MAIN_SIZE=0xC60000


def normal_usb_generation(serial,root=Path('/sys/bus/usb/devices'),physical_port=None):
    """Passive kernel attributes only: no USB handle/control request while waiting."""
    if os.name == 'nt' or sys.platform == 'darwin':return None  # No proven passive generation identifier on Windows.
    found=[]
    for node in root.glob('*'):
        try:
            if(node/'idVendor').read_text(encoding='utf-8').strip()!='04b8'or(node/'idProduct').read_text(encoding='utf-8').strip()!='11b1':continue
            if physical_port:
                if node.name!=physical_port:continue
            elif(node/'serial').read_text(encoding='utf-8').strip()!=serial:continue
            found.append(f"{int((node/'busnum').read_text(encoding='utf-8'))}:{int((node/'devnum').read_text(encoding='utf-8'))}")
        except (OSError,ValueError):continue
    return found[0]if len(found)==1 else None


def normal_usb_port(device,root=Path('/sys/bus/usb/devices')):
    if os.name == 'nt' or sys.platform == 'darwin':return None
    if not device:return None
    for node in root.glob('*'):
        try:
            if(node/'idVendor').read_text(encoding='utf-8').strip()!='04b8'or(node/'idProduct').read_text(encoding='utf-8').strip()!='11b1':continue
            generation=f"{int((node/'busnum').read_text(encoding='utf-8'))}:{int((node/'devnum').read_text(encoding='utf-8'))}"
            if generation==device:return node.name
        except (OSError,ValueError):continue
    return None


def require(condition,message):
    if not condition:raise ValueError(message)


def require_empty_queues():
    if os.name == 'nt':
        from .windows_printing import require_empty_queues as windows_check
        return windows_check()
    result=subprocess.run(['lpstat','-W','not-completed','-o'],capture_output=True,text=True,timeout=5)
    require(result.returncode==0 and not result.stdout.strip(),
            'Une file est active ou CUPS ne répond pas. Aucun travail ne sera supprimé.')


def normal_usb_device():
    if os.name == 'nt':
        from .windows_usb import normal_usb_device as windows_device
        return windows_device()
    from epson_usb.backends import find_devices
    devices=[d for d in find_devices(backend='libusb')if d.vendor_id==0x04b8]
    normal={d.path for d in devices if d.product_id==0x11b1}
    require(not any(d.product_id==0x0007 for d in devices),'Mode de secours MFP-IPL détecté. Ce programme ne flashe pas ce mode.')
    require(len(normal)==1,'Brancher une seule XP-2200 en USB normal (04b8:11b1).')
    return normal.pop()


def status_codes(raw):
    marker=b'@BDC ST2\r\n';start=raw.find(marker)
    require(start>=0,'État ST2 indisponible.')
    position=start+len(marker)+2;fields={}
    while position+2<=len(raw):
        kind,size=raw[position:position+2];position+=2
        require(position+size<=len(raw),'État ST2 tronqué.')
        fields[kind]=raw[position:position+size];position+=size
    require(fields.get(1)in(b'\x03',b'\x04')or(fields.get(1)==b'\x00'and fields.get(2)==b'\x05'),
            'L’Epson doit être au repos ; seule l’erreur de cartouche est admise avant installation.')


class V2Usb:
    def __init__(self,manifest,payload,serial):
        require(len(payload)==PAYLOAD_SIZE and hashlib.sha256(payload).hexdigest()==V2_SHA,'La charge utile n’est pas la V2 historique.')
        self.manifest,self.payload,self.serial=manifest,payload,serial
        self.printer=None;self.device=None;self.buffer=None;self.baseline=None;self.backup_confirmed=False
        self.staged=False

    def open(self):
        if sys.platform == 'darwin':
            from .macos_support import configure_libusb
            configure_libusb(required=True)
        require_empty_queues();self.device=normal_usb_device()
        self.printer=EpsonUsbPrinter(read_key=(75,54),write_key=None,dry_run=True,backend='usbprint' if os.name == 'nt' else 'libusb',device=self.device,interface=1)
        return self.identity()

    def close(self,protocol=True):
        if self.printer:
            if not protocol and self.printer.session:self.printer.session.connected=False
            self.printer.close();self.printer=None

    def identity(self,require_idle=True):
        vi=self.printer.command(b'vi',b'\x04')or b''
        require(vi.strip(b'\0\f;')in(b'vi:04:06.58.IU05P2.FY22',b'06.58.IU05P2.FY22'),'Version IU05P2 exacte non confirmée.')
        raw=self.printer.command(b'st',b'\x01')or b''
        types=self.printer.command(b'ia',b'\x00')or b''
        snapshot=parse_status(raw,'USB',types,vi)
        require(snapshot.serial==self.serial,'Numéro de série différent de l’imprimante sélectionnée.')
        if require_idle:status_codes(raw)
        snapshot.transport='USB'
        return snapshot

    def _memory(self,address,count):
        require(1<=count<=236,'Lecture mémoire hors limite.')
        fixed={0x42329520:32,0x42328548:16,0x42BBFD84:20,0x43E45C00:64}
        flash=FLASH_BASE<=address<address+count<=FLASH_BASE+FLASH_SIZE
        code=any(int(start)<=address and address+count<=int(start)+len(bytes.fromhex(value))
                 for start,value in self.manifest['baselines']['V2']['code_windows'].items())
        buffered=self.buffer is not None and self.buffer<=address<address+count<=self.buffer+MAIN_SIZE
        require(flash or code or fixed.get(address)==count or buffered,'Lecture hors des régions IU05P2 validées.')
        frame=b'K6\x00\xff\x00'+struct.pack('>I',address)+b'\0'+struct.pack('>H',count)
        reply=self.printer.command(b'||',frame)
        prefix=b'@BDC PS\r\nMT:'
        require(reply is not None and reply.startswith(prefix)and reply.endswith(b';\x0c'),'Réponse de lecture mémoire invalide.')
        data=reply[len(prefix):-2]
        require(len(data)==count,'Lecture mémoire incomplète.')
        return data

    def _flash_chunks(self,start,count,progress):
        end=start+count;offset=start
        while offset<end:
            boundary=min(end,offset+0x40000)
            while offset<boundary:
                size=min(236,boundary-offset)
                yield offset,self._memory(FLASH_BASE+offset,size)
                offset+=size
            progress(offset-start,count)
            if offset<end:
                self.close();self.open()

    def backup(self,destination,progress):
        require(self.printer is not None,'Session USB absente.')
        with destination.open('xb')as stream:
            destination.chmod(0o600)
            for _,data in self._flash_chunks(0,FLASH_SIZE,progress):stream.write(data)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        data=destination.read_bytes()
        require(len(data)==FLASH_SIZE,'Sauvegarde incomplète.')
        require(hashlib.sha256(data[:MAIN_OFFSET]).hexdigest()==self.manifest['boot_sha256'],
                'Programme de secours différent de la sauvegarde historique ; arrêt avant transfert.')
        digest=hashlib.sha256(data[MAIN_OFFSET:MAIN_OFFSET+MAIN_SIZE]).hexdigest()
        matches=[name for name,item in self.manifest['baselines'].items()if item['main_sha256']==digest]
        require(len(matches)==1,'Programme actuel inconnu, altéré ou V3 : aucun transfert autorisé.')
        self.baseline=matches[0]
        self._check_code(self.baseline)
        self.backup_confirmed=True
        return {'baseline':self.baseline,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}

    def _check_code(self,baseline):
        require(self._memory(0x43E45C00,64)==bytes.fromhex(self.manifest['public_key']),'Clé publique IU05P2 différente.')
        for address,data in self.manifest['baselines'][baseline]['code_windows'].items():
            expected=bytes.fromhex(data)
            require(self._memory(int(address),len(expected))==expected,'Instructions RAM différentes de l’image identifiée.')

    def _control(self,payload,expected):
        session=self.printer.session;session.send(0,0,payload,credit=1)
        for _ in range(8):
            packet=wait_packet(session,1000)
            if packet is None:continue
            require(packet.psid==0 and packet.payload[:2]==bytes((expected,0)),'Réponse de contrôle D4 inattendue.')
            return packet.payload[2:]
        raise ValueError('Délai D4 dépassé ; aucun nouvel essai de flash automatique.')

    def stage(self,progress,before_update):
        require(self.backup_confirmed and self.baseline in {'official','V1'},'Sauvegarde et programme de départ non validés.')
        require_empty_queues();self.identity()
        manager=self._memory(0x42329520,32)
        require(manager[5]==0 and manager[8:10]==b'\0\0','Gestionnaire de mise à jour occupé.')
        response=self._control(b'\x09EPSON-DATA',0x89)
        require(len(response)>=1 and response[0]not in(0,2)and response[1:]in(b'',b'EPSON-DATA'),'Canal de transfert inattendu.')
        sid=response[0];session=self.printer.session
        # The journal is durable before the first mutating command, even if
        # its reply is lost. Failure after this point requires verification.
        before_update()
        reply=self.printer.command(b'gm',b'\x01')
        require(reply==b'fl:01:OK;\x0c','Entrée en transfert non confirmée ; pas de validation de flash.')
        session.extra_socket_pairs={(sid,sid)}
        response=self._control(struct.pack('>BBBHHHH',1,sid,sid,4096,4096,0,0),0x81)
        require(len(response)==8,'Négociation du canal de données invalide.')
        psid,ssid,mtu,_,credit=struct.unpack('>BBHHH',response)
        require((psid,ssid)==(sid,sid)and 256<=mtu<=4096,'Taille de transfert non validée.')
        offset=0;last=0
        while offset<len(self.payload):
            deadline=time.monotonic()+15
            while credit==0:
                response=self._control(struct.pack('>BBBHH',4,sid,sid,128,0xFFFF),0x84)
                require(len(response)==4 and response[:2]==bytes((sid,sid)),'Crédit D4 inattendu.')
                credit=int.from_bytes(response[2:],'big')
                if not credit:
                    require(time.monotonic()<deadline,'Aucun crédit de transfert pendant quinze secondes.')
                    time.sleep(.1)
            part=self.payload[offset:offset+mtu-6];final=offset+len(part)==len(self.payload)
            session.send(sid,sid,part,credit=0,control=2 if final else 0)
            credit-=1;offset+=len(part)
            if offset-last>=0x40000 or final:progress(offset,len(self.payload));last=offset
        require(self._control(bytes((2,sid,sid)),0x82)==bytes((sid,sid)),'Fermeture du canal non confirmée.')
        for _ in range(60):
            manager=self._memory(0x42329520,32)
            if manager[9]==6:break
            require(manager[9]==5,'Le chargeur a refusé la mise à jour.')
            time.sleep(.5)
        self._verify_staged()
        self.staged=True

    def _verify_staged(self):
        manager=self._memory(0x42329520,32);stream=self._memory(0x42328548,16)
        metadata=self._memory(0x42BBFD84,20)
        if self.staged:require(metadata==self.metadata,'Les métadonnées du tampon ont changé depuis le transfert.')
        require(manager[5]==2 and manager[8:10]==b'\x01\x06','Image non prête à être validée.')
        require(stream[0]==1 and int.from_bytes(stream[4:8],'little')==1,'État du lecteur différent du V2 historique.')
        pointer,capacity,destination,length=struct.unpack_from('<4I',metadata)
        require((destination,length,metadata[18])==(MAIN_OFFSET,MAIN_SIZE,0),'Destination de flash non autorisée.')
        require(capacity>=length and 0x42000000<=pointer<pointer+length<=0x54000000,'Tampon de transfert hors plage.')
        require(int.from_bytes(metadata[16:18],'little')==sum(self.payload[0x4000:])&65535,'Somme du principal incorrecte.')
        self.buffer=pointer
        offsets={0,0x90000,*range(0x94000,0xE4000,0x4000),0x100000,0x59A000,0xC5FFC0}
        offsets|={sector*65536-MAIN_OFFSET for sector in range(12,17)}
        for offset in sorted(offsets):
            require(self._memory(pointer+offset,64)==self.payload[0x4000+offset:0x4040+offset],'Échantillon du tampon différent de la V2.')
        self.metadata=metadata

    def commit(self,before_commit):
        require(self.staged,'Aucun transfert V2 validé dans cette session.')
        require_empty_queues();self._verify_staged()
        require(self._memory(0x42BBFD84,20)==self.metadata,'Les métadonnées ont changé.')
        self.pre_commit_device=self.device
        self.pre_commit_port=normal_usb_port(self.device)
        before_commit()
        try:
            # Sent exactly once. A timeout can mean programming has started;
            # never retry it and never send protocol cleanup afterwards.
            return self.printer.command(b'gm',b'\x03',tries=1)
        finally:self.close(protocol=False)

    def restarted_device(self):
        generation=normal_usb_generation(self.serial,physical_port=getattr(self,'pre_commit_port',None))
        return generation if generation and generation!=getattr(self,'pre_commit_device',None)else None

    def quick_verify(self,progress):
        """All modified sectors + all recovery bytes + exact RAM patches/key/header.

        This is explicitly a targeted check, not a full-image SHA comparison.
        Allowed only after the caller has identified a normal reboot, or after
        a complete pre-operation backup already identified installed V2.
        """
        self.open();quick=self.manifest['quick_range'];total=quick['length']+MAIN_OFFSET
        digest=hashlib.sha256()
        for _,data in self._flash_chunks(quick['offset'],quick['length'],lambda done,_:progress(done,total)):
            digest.update(data)
        require(digest.hexdigest()==self.manifest['baselines']['V2']['quick_sha256'],'Les secteurs modifiés V2 ne sont pas confirmés.')
        boot=hashlib.sha256()
        for _,data in self._flash_chunks(0,MAIN_OFFSET,lambda done,_:progress(quick['length']+done,total)):boot.update(data)
        require(boot.hexdigest()==self.manifest['boot_sha256'],'Le programme de secours ne correspond plus.')
        require(self._memory(FLASH_BASE+MAIN_OFFSET,64)==bytes.fromhex(self.manifest['main_header']),'En-tête du programme principal différent.')
        self._check_code('V2');snapshot=self.identity()
        require(snapshot.chipless is True,'Contournement des puces non confirmé.')
        self.verified_baseline='V2';self.verification_scope='modified_regions_and_boot'
        return snapshot

    def verify(self,progress,allow_unchanged=False):
        self.open()
        digest=hashlib.sha256()
        for _,data in self._flash_chunks(MAIN_OFFSET,MAIN_SIZE,progress):digest.update(data)
        matches=[name for name,item in self.manifest['baselines'].items()if item['main_sha256']==digest.hexdigest()]
        require(len(matches)==1,'Le programme principal V2 n’est pas confirmé : image inconnue.')
        baseline=matches[0]
        require(allow_unchanged or baseline=='V2','V2 non installée : programme '+baseline+' détecté.')
        boot=hashlib.sha256()
        for _,data in self._flash_chunks(0,MAIN_OFFSET,lambda *_:None):boot.update(data)
        require(boot.hexdigest()==self.manifest['boot_sha256'],'Le programme de secours ne correspond plus.')
        self._check_code(baseline)
        snapshot=self.identity()
        if baseline=='V2':require(snapshot.chipless is True,'Contournement des puces non confirmé après relecture V2.')
        self.verified_baseline=baseline
        self.verification_scope='full'
        return snapshot
