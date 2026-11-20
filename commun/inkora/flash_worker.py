"""Durable, single-operation V2 state machine. No automatic flash retry."""
import json
import os
from pathlib import Path
import sqlite3
import time

from .firmware import (COOLDOWN_SECONDS,SAFE_PHASES,V2_SHA,atomic_json,boot_id,current_operation,
                       firmware_root,hardware_session,job_folder,load_assets,remaining_wait,utc_now,validate_plan)
from .firmware_usb import V2Usb
from .store import Store
from .printer import Snapshot
from .branding import RISK_NOTICE_VERSION


def stop_monitor(database):
    from .service import request
    try:request(database,'stop')
    except OSError:return
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        try:request(database,'ping')
        except OSError:return
        time.sleep(.2)
    raise ValueError('L’agent n’a pas terminé sa lecture. Installation non commencée.')


class FlashJob:
    def __init__(self,identifier,backend_factory=V2Usb,clock=time.time,sleep=time.sleep,
                 stop_monitoring=stop_monitor,restart_monitoring=None,monotonic=time.monotonic):
        self.identifier=identifier;self.folder=job_folder(identifier)
        self.request=json.loads((self.folder/'request.json').read_text(encoding='utf-8'))
        if self.request.get('id')!=identifier or self.request.get('confirmed')is not True or self.request.get('payload_sha256')!=V2_SHA:
            raise ValueError('Demande d’installation invalide.')
        self.request['plan']=validate_plan(self.request['plan'])
        if not self.request.get('serial'):raise ValueError('Identité absente.')
        self.backend_factory=backend_factory;self.clock=clock;self.sleep=sleep
        self.monotonic=monotonic
        self.stop_monitoring=stop_monitoring
        if restart_monitoring is None:
            from .service import ensure_agent
            restart_monitoring=ensure_agent
        self.restart_monitoring=restart_monitoring
        previous_path=self.folder/'progress.json'
        self.state=json.loads(previous_path.read_text(encoding='utf-8'))if previous_path.exists()else{
            'id':identifier,'phase':'prepared','detail':'Installation préparée, aucune commande envoyée.',
            'update_mode_attempted':False,'commit_attempted':False,'verified':False,'levels_applied':False}

    def emit(self,phase,detail,**values):
        self.state.update(phase=phase,detail=detail,updated_at=utc_now(),**values)
        atomic_json(self.folder/'progress.json',self.state)
        atomic_json(firmware_root()/'current.json',self.state)

    def deadline(self):
        return {'no_contact_before':self.clock()+COOLDOWN_SECONDS,
                'no_contact_before_uptime':self.monotonic()+COOLDOWN_SECONDS,'boot_id':boot_id()}

    def before_update(self):
        self.emit('upload','Transfert d’OpenFlow ; garder les câbles branchés.',update_mode_attempted=True,
                  **self.deadline(),progress=0)

    def before_commit(self):
        self.emit('commit_requested','Image OpenFlow contrôlée ; demande unique de programmation.',commit_attempted=True,
                  **self.deadline(),progress=0)

    def progress(self,phase,label,done,total):
        extra={'progress':round(done/max(1,total),4)}
        if phase=='upload':extra.update(self.deadline())
        self.emit(phase,label,**extra)

    def _backup_database(self):
        source=sqlite3.connect(self.request['database'])
        target=sqlite3.connect(self.folder/'inkora-before.sqlite3')
        try:
            source.backup(target)
        finally:target.close();source.close()
        (self.folder/'inkora-before.sqlite3').chmod(0o600)

    def _save_followup(self,snapshot):
        store=None
        try:
            store=Store(self.request['database'])
            store.observe(snapshot)
            applied=store.apply_firmware_plan(snapshot,self.request['plan'],self.identifier,
                                             Snapshot(**self.request['before_snapshot']))
            store.check_alerts(snapshot)
            missing=[color for color,estimate in store.estimates(snapshot).items()if estimate is None]
        except Exception as exc:
            # Firmware verification has succeeded. A database/ink-ledger issue
            # must not be reported as a failed flash or cause another upload.
            self.emit('done','OpenFlow vérifié ; suivi à revoir dans Cartouches : '+str(exc),
                      verified=True,levels_applied=False,followup_error=str(exc),snapshot=snapshot.to_dict(),progress=1,
                      no_contact_before=0,no_contact_before_uptime=0,remaining_seconds=0)
            return
        finally:
            if store:store.close()
        self.emit('done','OpenFlow vérifié. '+('Estimations à renseigner : '+', '.join(missing)if missing else'Suivi de l’encre prêt.'),
                  verified=True,levels_applied=True,followup_newly_applied=applied,untracked_colors=missing,
                  snapshot=snapshot.to_dict(),progress=1)
        self.emit('done',self.state['detail'],no_contact_before=0,no_contact_before_uptime=0,remaining_seconds=0)

    def _await_normal_restart(self,backend):
        start=self.monotonic();stable_generation=None;stable_since=start;last_update=-5
        while self.monotonic()-start<90:
            now=self.monotonic();generation=backend.restarted_device()
            if generation!=stable_generation:
                stable_generation=generation;stable_since=now
            if generation and now-stable_since>=3 and now-start>=10:
                self.emit('restarted','Redémarrage USB normal détecté. Contrôle ciblé d’OpenFlow.',restart_generation=generation)
                return True
            if now-start-last_update>=5:
                self.emit('restarting','Détection du redémarrage USB normal ; ne pas débrancher.',
                          progress=None,wait_mode='restart_detection')
                last_update=now-start
            self.sleep(1)
        return False

    def run(self,verify_only=False):
        # Root is unnecessary and would create an agent with the wrong session.
        if os.name != 'nt' and os.geteuid()==0:raise ValueError('Lancer Inkora dans la session utilisateur, sans sudo.')
        if not verify_only and self.state['phase']!='prepared':
            raise ValueError('Une opération existante ne peut pas être reflashée ; créer une nouvelle préparation si nécessaire.')
        if not verify_only and(self.request.get('risk_acknowledged')is not True or self.request.get('usb_confirmed')is not True
                               or self.request.get('risk_notice_version')!=RISK_NOTICE_VERSION):
            raise ValueError('Reprépare l’installation avec l’acceptation des risques et la confirmation USB obligatoire.')
        current=current_operation()
        if current and current['phase']not in SAFE_PHASES:
            if not verify_only or current.get('id')!=self.identifier:
                raise ValueError('Vérifier l’opération précédente ; aucun nouveau flash ne sera envoyé.')
        if verify_only and (current is None or current.get('id')!=self.identifier):
            raise ValueError('Aucune opération correspondante à vérifier.')
        if verify_only and remaining_wait(self.state,self.clock,self.monotonic):
            raise ValueError('Le délai de quinze minutes n’est pas terminé. Aucune communication envoyée.')
        manifest,payload=load_assets()
        self.stop_monitoring(self.request['database'])
        with hardware_session(firmware=True):
            # Recheck after the exclusive lease, avoiding two prepared jobs
            # racing each other while their agents finish.
            current=current_operation()
            if current and current['phase']not in SAFE_PHASES and current.get('id')!=self.identifier:
                raise ValueError('Une autre opération OpenFlow est en cours.')
            backend=self.backend_factory(manifest,payload,self.request['serial'])
            try:
                if verify_only:
                    self.emit('verifying','Vérification seule ; aucun transfert ni flash envoyé.',progress=0)
                    snapshot=backend.verify(lambda done,total:self.progress('verifying','Relecture du programme installé.',done,total),allow_unchanged=True)
                    self.state['verification_scope']=getattr(backend,'verification_scope','full')
                    baseline=getattr(backend,'verified_baseline','V2')
                    if baseline=='V2':self._save_followup(snapshot)
                    else:
                        self.emit('unchanged','OpenFlow non installé ; programme '+baseline+' reconnu et intact. Niveaux conservés. Une nouvelle préparation manuelle est possible.',
                                  verified=False,levels_applied=False,baseline_detected=baseline,snapshot=snapshot.to_dict(),progress=1)
                else:
                    if self.state.get('update_mode_attempted')or self.state.get('verified'):
                        raise ValueError('Cette opération ne peut pas être flashée une seconde fois.')
                    self.emit('checking','Contrôle USB, identité, firmware et files d’impression.',progress=0)
                    backend.open()
                    self._backup_database()
                    backup=backend.backup(self.folder/'printer-before.bin',
                        lambda done,total:self.progress('backup','Sauvegarde intégrale de l’imprimante avant transfert.',done,total))
                    self.emit('checked','Sauvegarde complète et programme de départ reconnus.',backup=backup,progress=1)
                    if backup['baseline']=='V2':
                        self.emit('verifying','OpenFlow déjà installé : aucun nouveau flash nécessaire.',progress=0)
                        backend.close()
                        snapshot=backend.quick_verify(lambda done,total:self.progress('verifying','Contrôle ciblé d’OpenFlow déjà installée.',done,total))
                        self.state['verification_scope']=getattr(backend,'verification_scope','modified_regions_and_boot')
                        self._save_followup(snapshot)
                    else:
                        backend.stage(lambda done,total:self.progress('upload','Transfert OpenFlow ; ne pas débrancher.',done,total),self.before_update)
                        self.emit('staged','Tampon OpenFlow contrôlé : métadonnées, somme et échantillons.',progress=1)
                        reply=backend.commit(self.before_commit)
                        self.state['commit_reply_hex']=(reply or b'').hex()
                        if reply==b'fl:03:OK;\x0c'and self._await_normal_restart(backend):
                            self.emit('verifying','Redémarrage reconnu. Vérification des secteurs modifiés et du secours.',progress=0)
                            snapshot=backend.quick_verify(lambda done,total:self.progress('verifying','Contrôle des secteurs OpenFlow modifiés et du secours.',done,total))
                            self.state['verification_scope']=getattr(backend,'verification_scope','modified_regions_and_boot')
                        else:
                            self.emit('waiting','Redémarrage non confirmé. Attente prudente après programmation.',progress=0,wait_mode='conservative')
                            while remaining_wait(self.state,self.clock,self.monotonic):
                                remaining=remaining_wait(self.state,self.clock,self.monotonic)
                                self.emit('waiting','Ne pas intervenir : attente de sécurité après programmation.',
                                          remaining_seconds=int(remaining),progress=1-remaining/COOLDOWN_SECONDS)
                                self.sleep(min(5,remaining))
                            self.emit('verifying','Attente terminée. Vérification complète du programme OpenFlow.',progress=0)
                            snapshot=backend.verify(lambda done,total:self.progress('verifying','Relecture complète du programme OpenFlow.',done,total))
                            self.state['verification_scope']='full'
                        self._save_followup(snapshot)
            except Exception as exc:
                touched=self.state.get('update_mode_attempted',False)
                if touched:
                    deadline=self.deadline()if self.state['phase']not in {'waiting','verifying','done'}else{}
                    self.emit('verification_required','Résultat non confirmé. Aucun nouveau flash automatique. '+str(exc),
                              **deadline,error=str(exc),verified=False)
                    # A lost reply can mean the printer is already programming.
                    # Keep the lease and sleep inhibitor alive for the complete
                    # quiet period, including the error path, without USB I/O.
                    backend.close(protocol=False)
                    while remaining_wait(self.state,self.clock,self.monotonic):
                        remaining=remaining_wait(self.state,self.clock,self.monotonic)
                        self.emit('verification_required','Résultat non confirmé. Attendre sans débrancher : '+str(exc),
                                  remaining_seconds=remaining,progress=1-remaining/COOLDOWN_SECONDS)
                        self.sleep(min(5,remaining))
                    self.emit('verification_required','Attente terminée. Vérifier l’installation ; aucun nouveau flash automatique. '+str(exc),
                              remaining_seconds=0,progress=1)
                else:
                    self.emit('failed_before_update','Arrêt avant transfert : '+str(exc),error=str(exc))
            finally:
                # After any attempted commit no packet is sent merely to tidy
                # up. Verification sessions close normally after they finish.
                backend.close(protocol=not(self.state.get('commit_attempted')and self.state['phase']=='verification_required'))
        if self.state['phase']in SAFE_PHASES:
            try:self.restart_monitoring(self.request['database'])
            except Exception as exc:
                self.state['monitor_restart_error']=str(exc)
                atomic_json(self.folder/'progress.json',self.state)
                atomic_json(firmware_root()/'current.json',self.state)
        return bool(self.state.get('verified'))


def run_job(identifier,verify_only=False):
    if os.name == 'nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.SetThreadExecutionState.argtypes=[ctypes.c_uint]
        kernel.SetThreadExecutionState.restype=ctypes.c_uint
        if not kernel.SetThreadExecutionState(0x80000001):
            raise OSError('Impossible d’empêcher la veille ; opération non commencée.')
        try:
            job=FlashJob(identifier)
            return 0 if job.run(verify_only) else 1
        finally:kernel.SetThreadExecutionState(0x80000000)
    job=FlashJob(identifier)
    return 0 if job.run(verify_only)else 1
