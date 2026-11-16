"""Pinned V2 assets, private operation journal and explicit worker launcher.

Importing this module never opens a printer. All ordinary readers share a
lease with the firmware worker and honour an interrupted operation's journal.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from functools import lru_cache
import shutil
import subprocess
import time
import uuid

from .printer import COLORS,NAMES
from .branding import RISK_NOTICE_VERSION

V2_SHA='413718a144f982fcae8d6e9c2a3adc82d0aafd99dbcb635105411c22f53348ef'
MANIFEST_SHA='268d46f9ef07524c9a80ba2c7919e43ba89fed0988a3b706364949a44eb6a3a4'
PAYLOAD_SIZE=0xC64000
COOLDOWN_SECONDS=15*60
SAFE_PHASES={'done','failed_before_update','unchanged'}


def utc_now():return datetime.now(timezone.utc).isoformat()


def private_directory(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink()or path.stat().st_uid!=os.getuid():
        raise ValueError('Le dossier OpenInk doit appartenir à cet utilisateur.')
    path.chmod(0o700)
    return path


def firmware_root():
    return private_directory(Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'inkora/firmware')


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8')as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:temporary.unlink(missing_ok=True)


def load_assets():
    folder=Path(__file__).parent/'firmware_assets'
    encoded=(folder/'v2.json').read_bytes()
    if hashlib.sha256(encoded).hexdigest()!=MANIFEST_SHA:raise ValueError('Description V2 altérée ; opération refusée.')
    manifest=json.loads(encoded)
    with gzip.open(folder/'xp2200-v2.bin.gz','rb')as stream:payload=stream.read(PAYLOAD_SIZE+1)
    if len(payload)!=PAYLOAD_SIZE or hashlib.sha256(payload).hexdigest()!=V2_SHA:
        raise ValueError('Firmware différent de la V2 vérifiée ; opération refusée.')
    if manifest['variant']!='V2'or manifest['warning_prototype_included']:
        raise ValueError('Seule la V2 historique est autorisée.')
    return manifest,payload


def current_operation():
    path=firmware_root()/'current.json'
    if not path.exists():return None
    result=json.loads(path.read_text())
    if not isinstance(result,dict)or'phase'not in result:raise ValueError('Journal firmware illisible ; contrôle manuel requis.')
    return result


def require_monitoring_allowed():
    operation=current_operation()
    if operation and operation['phase']not in SAFE_PHASES:
        raise ValueError('Suivi suspendu : opération V2 en cours ou installation à vérifier dans Firmware V2.')


def hardware_busy():
    path=firmware_root()/'hardware.lock'
    with path.open('a+b')as handle:
        path.chmod(0o600)
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(handle,fcntl.LOCK_UN)
    return False


@contextmanager
def hardware_session(firmware=False):
    # Shared by network and USB, across all OpenInk database choices.
    root=firmware_root();path=root/'hardware.lock'
    with path.open('a+b')as handle:
        path.chmod(0o600)
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Une communication OpenInk est déjà en cours. Réessaie après sa fin.')from None
        try:
            if not firmware:require_monitoring_allowed()
            yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def job_folder(identifier):
    if not isinstance(identifier,str)or len(identifier)!=32 or any(c not in'0123456789abcdef'for c in identifier):
        raise ValueError('Identifiant d’opération invalide.')
    return firmware_root()/'jobs'/identifier


def validate_plan(plan):
    if not isinstance(plan,dict)or any(c not in COLORS for c in plan):raise ValueError('Sélection de couleurs invalide.')
    result={}
    for color,item in plan.items():
        if not isinstance(item,dict)or item.get('action')not in {'keep','full','estimate'}:raise ValueError('Opération d’encre invalide.')
        action=item['action'];value={'action':action}
        if action!='keep':
            amount=float(item.get('percent',-1))
            if not math.isfinite(amount)or not 0<=amount<=100:raise ValueError(NAMES[color]+' : saisir un niveau entre 0 et 100 %.')
            if action=='full'and(amount!=100 or item.get('ink_added')is not True):
                raise ValueError('Confirme le remplissage réel avant de déclarer 100 %.')
            profile=item.get('profile','604');capacity=item.get('capacity')
            if profile not in {'604','604XL','Personnalisé'}:raise ValueError('Format de cartouche invalide.')
            if profile=='Personnalisé'and(not isinstance(capacity,int)or isinstance(capacity,bool)or not 1<=capacity<=100000):
                raise ValueError('Rendement personnalisé invalide.')
            value.update(percent=amount,profile=profile,capacity=capacity,ink_added=action=='full')
        result[color]=value
    return result


def prepare_job(database,snapshot,plan,estimates,confirmed=False,*,risk_acknowledged=False,usb_confirmed=False):
    if not confirmed:raise ValueError('La validation explicite de l’installation est nécessaire.')
    if risk_acknowledged is not True:raise ValueError('Lis l’avertissement et accepte explicitement les risques du flash.')
    if usb_confirmed is not True:raise ValueError('Le flash doit obligatoirement se faire par câble USB.')
    if snapshot is None or snapshot.demo or not snapshot.serial or snapshot.printer_id!=snapshot.serial:
        raise ValueError('Identité réelle de l’Epson non confirmée.')
    if snapshot.firmware!='06.58.IU05P2.FY22':raise ValueError('Firmware différent de IU05P2 ; installation refusée.')
    if snapshot.color_pages is None or snapshot.mono_pages is None:raise ValueError('Compteurs de pages indisponibles.')
    plan=validate_plan(plan)
    for color in COLORS:
        if (color not in plan or plan[color]['action']=='keep')and estimates.get(color)is None:
            raise ValueError(NAMES[color]+' : renseigne une estimation de départ avant de retirer le blocage d’encre.')
    load_assets()
    with hardware_session(firmware=True):
        previous=current_operation()
        if previous and previous['phase']not in SAFE_PHASES:
            raise ValueError('L’opération précédente doit être vérifiée avant toute nouvelle installation.')
        identifier=uuid.uuid4().hex;folder=private_directory(firmware_root()/'jobs'/identifier)
        request={'id':identifier,'database':str(Path(database).resolve()),'serial':snapshot.serial,'plan':plan,
                 'confirmed':True,'created_at':utc_now(),'payload_sha256':V2_SHA,
                 'risk_acknowledged':True,'risk_notice_version':RISK_NOTICE_VERSION,'usb_confirmed':True,
                 'before_estimates':estimates,'before_snapshot':snapshot.to_dict()}
        atomic_json(folder/'request.json',request)
        # A prepared job has not touched USB and does not suspend monitoring.
    return identifier


def read_job(identifier):
    folder=job_folder(identifier)
    return json.loads((folder/'request.json').read_text()),json.loads((folder/'progress.json').read_text())if(folder/'progress.json').exists()else None


def launch_job(identifier,verify_only=False):
    from .service import launch_environment
    import sys
    job_folder(identifier)  # Validate before constructing arguments.
    inhibit=shutil.which('systemd-inhibit')
    if not inhibit:raise ValueError('systemd-inhibit est requis pour empêcher la veille pendant l’installation.')
    command=[inhibit,'--what=sleep:idle','--mode=block','--who=OpenInk',
             '--why=Installation et vérification du firmware V2 Epson',sys.executable,'-m','inkora','--firmware-job',identifier]
    if verify_only:command.append('--verify-firmware')
    folder=job_folder(identifier);log=folder/'worker.log'
    with log.open('ab')as stream:
        log.chmod(0o600)
        return subprocess.Popen(command,env=launch_environment(),stdout=stream,stderr=stream,start_new_session=True)


@lru_cache(maxsize=1)
def boot_id():
    try:return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:return ''


def remaining_wait(operation,clock=time.time,uptime=time.monotonic):
    state=operation or{}
    if not state.get('no_contact_before'):return 0
    wall=float(state['no_contact_before'])-clock()
    if state.get('boot_id')and state['boot_id']==boot_id():
        steady=float(state.get('no_contact_before_uptime',0))-uptime()
    else:
        # Following an interrupted operation and a computer reboot, allow a
        # full 15 minutes since boot as well as the persisted wall deadline.
        steady=COOLDOWN_SECONDS-uptime()
    return max(0,int(math.ceil(max(wall,steady))))
