"""Local presentation translations. Protocol values and stored data stay canonical."""
from functools import lru_cache
from contextlib import closing
import json
import locale
import os
from pathlib import Path
import re
import sqlite3
import string
import sys

LANGUAGES={'auto':'Automatique','fr':'Français','en':'English','es':'Español'}
_language='fr'


def resolve_language(value='auto'):
    if value in('fr','en','es'):return value
    if value!='auto':return 'fr'
    values=[os.environ.get('LANGUAGE','').split(':')[0],os.environ.get('LC_ALL',''),
            os.environ.get('LC_MESSAGES',''),os.environ.get('LANG',''),locale.getlocale()[0]or'']
    for candidate in values:
        if candidate:
            code=re.split('[-_.]',candidate.lower())[0]
            return code if code in('fr','en','es')else'en'
    return 'fr'


def set_language(value):
    global _language
    _language=resolve_language(value)
    return _language


def get_language():return _language


def saved_language(database=None):
    """Read the preference without creating/migrating the user database."""
    if database is None:
        from .store import default_database
        database=default_database()
    path=Path(database)
    if not path.is_file():return 'auto'
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.3))as db:
            row=db.execute("SELECT value FROM settings WHERE key='language'").fetchone()
            value=json.loads(row[0])if row else'auto'
            return value if isinstance(value,str)and value in LANGUAGES else'auto'
    except(sqlite3.Error,ValueError,OSError):return 'auto'


@lru_cache(maxsize=2)
def catalog(language):
    return json.loads((Path(__file__).parent/'locales'/f'{language}.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=2)
def patterns(language):
    result=[]
    for source,target in catalog(language).items():
        if '{p'not in source:continue
        pieces=[];fields=[]
        for literal,field,spec,conversion in string.Formatter().parse(source):
            pieces.append(re.escape(literal))
            if field is not None:pieces.append('(.*?)');fields.append(field)
        result.append((re.compile('^'+''.join(pieces)+'$',re.S),fields,target,len(source)))
    return sorted(result,key=lambda row:row[3],reverse=True)


def tr(value):
    translated=_translate(value,_language,0)
    if os.name == 'nt' and isinstance(translated,str):
        translated=translated.replace('d’Ubuntu','de Windows').replace('Ubuntu','Windows').replace('CUPS','Windows')
    if sys.platform == 'darwin' and isinstance(translated,str):
        translated=translated.replace('d’Ubuntu','de macOS').replace('Ubuntu','macOS')
    return translated


@lru_cache(maxsize=2)
def prefixes(language):
    return sorted(((source,target)for source,target in catalog(language).items()
                   if len(source)>6 and source.endswith((': ',' : ','  '))),key=lambda pair:len(pair[0]),reverse=True)


def _translate(value,language,depth):
    if not isinstance(value,str)or language=='fr'or not value or not any(c.isalpha()for c in value):return value
    words=catalog(language)
    if value in words:return words[value]
    if depth>6 or len(value)>8192:return value
    for pattern,fields,target,_ in patterns(language):
        match=pattern.fullmatch(value)
        if match:
            return target.format(**{field:_translate(part,language,depth+1)
                                    for field,part in zip(fields,match.groups())})
    stripped=value.strip()
    if stripped!=value:
        translated=_translate(stripped,language,depth+1)
        if translated!=stripped:return value[:len(value)-len(value.lstrip())]+translated+value[len(value.rstrip()):]
    if value.isupper():
        source=next((key for key in words if key.casefold()==value.casefold()),None)
        if source:return words[source].upper()
    for source,target in prefixes(language):
        if value.startswith(source):return target+_translate(value[len(source):],language,depth+1)
    for separator in('\n',' · ',' : '):
        if separator in value:
            return separator.join(_translate(part,language,depth+1)for part in value.split(separator))
    return value


def test_page():
    from .branding import ASSETS
    filename='test-page.pdf'if _language=='fr'else f'test-page.{_language}.pdf'
    return ASSETS/filename
