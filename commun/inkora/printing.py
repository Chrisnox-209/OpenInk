"""A single explicit test-page job through CUPS, never a default printer."""
from datetime import datetime,timezone
import os
import re
import subprocess
from urllib.parse import urlsplit,parse_qs,unquote

from .branding import TEST_PAGE
from .i18n import test_page,tr
from .firmware import hardware_session

ENV={**os.environ,'LC_ALL':'C'}


def cups_printers(snapshot):
    result=subprocess.run(['lpstat','-v'],capture_output=True,text=True,timeout=5,env=ENV)
    if result.returncode:raise ValueError('CUPS ne répond pas : '+result.stderr.strip())
    states=subprocess.run(['lpstat','-p'],capture_output=True,text=True,timeout=5,env=ENV)
    if states.returncode:raise ValueError('Impossible de lire l’état des files CUPS : '+states.stderr.strip())
    disabled={match.group(1)for line in states.stdout.splitlines()
              if(match:=re.match(r'printer (\S+) disabled\b',line))}
    printers=[]
    for line in result.stdout.splitlines():
        match=re.match(r'device for ([A-Za-z0-9_][A-Za-z0-9_.-]*):\s*(.+)$',line)
        if not match:continue
        name,uri=match.groups()
        if 'mfp-ipl'in(name+' '+uri).lower():continue
        decoded=unquote(uri);model='xp2200'in re.sub('[^a-z0-9]','',(name+' '+decoded).lower())
        parsed=urlsplit(uri);query=parse_qs(parsed.query)
        serials=set(query.get('serial',[]))
        for serial in tuple(serials):
            try:serials.add(bytes.fromhex(serial).decode('ascii'))
            except (ValueError,UnicodeDecodeError):pass
        serial_match=bool(snapshot and snapshot.serial and snapshot.serial in serials)
        host_match=bool(snapshot and snapshot.transport!='USB'and parsed.hostname==snapshot.host)
        confirmed=serial_match or host_match
        if model or confirmed:printers.append({'name':name,'confirmed':confirmed,'enabled':name not in disabled,'uri':uri})
    return sorted(printers,key=lambda item:(not item['enabled'],not item['confirmed'],item['name']))


def submit_test_page(snapshot,queue,confirm_destination=False):
    if snapshot.demo:raise ValueError('Le mode démonstration ne peut pas imprimer.')
    if not snapshot.ready:raise ValueError('L’Epson doit être prête avant d’envoyer la page de test.')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(snapshot.observed_at)).total_seconds()
    if not 0<=age<=120:raise ValueError('Actualise l’imprimante avant d’imprimer la page de test.')
    if not isinstance(queue,str)or not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]{0,126}',queue):
        raise ValueError('Choisis une file Epson valide.')
    page=test_page()
    if not page.is_file():raise ValueError('La page de test OpenInk est introuvable.')
    with hardware_session():
        selected=next((p for p in cups_printers(snapshot)if p['name']==queue),None)
        if not selected:raise ValueError('Cette file Epson n’est plus disponible.')
        if not selected['enabled']:
            raise ValueError('Cette file CUPS est désactivée. Choisis une file disponible, ou réactive-la dans les paramètres Imprimantes d’Ubuntu.')
        if not selected['confirmed']and not confirm_destination:
            raise ValueError('Confirme que la file choisie correspond à ton Epson.')
        jobs=subprocess.run(['lpstat','-W','not-completed','-o',queue],capture_output=True,text=True,timeout=5,env=ENV)
        if jobs.returncode or jobs.stdout.strip():raise ValueError('Cette file est occupée. Attends la fin du document en cours.')
        # No shell, no default queue, one copy, no duplex or implicit reprint.
        result=subprocess.run(['lp','-d',queue,'-n','1','-t',tr('OpenInk - page de test CMJN'),
             '-o','media=A4','-o','sides=one-sided','-o','print-color-mode=color',str(page)],
             capture_output=True,text=True,timeout=15,env=ENV)
        if result.returncode:raise ValueError('Envoi refusé par CUPS : '+result.stderr.strip())
        match=re.search(r'request id is ([A-Za-z0-9_.-]+-\d+)',result.stdout)
        return {'accepted':True,'job_id':match.group(1)if match else None,'queue':queue,
                'printed_verified':False,'copies':1}
