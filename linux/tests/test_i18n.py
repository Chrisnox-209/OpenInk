"""Translation boundaries: data, firmware and printer identifiers stay canonical."""
import argparse
from contextlib import redirect_stderr,redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import string
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.i18n import catalog,set_language,get_language,resolve_language,saved_language,tr,test_page
from inkora.store import Store
from inkora.branding import RISK_NOTICE


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='openink-languages-')
        self.path=Path(self.temp.name)/'test.sqlite3';set_language('fr')
    def tearDown(self):set_language('fr');self.temp.cleanup()

    def test_catalogues_have_matching_keys_and_placeholders(self):
        self.assertEqual(set(catalog('en')),set(catalog('es')))
        fields=lambda s:{field for _,field,_,_ in string.Formatter().parse(s)if field is not None}
        for language in('en','es'):
            self.assertGreater(len(catalog(language)),450)
            for source,target in catalog(language).items():
                self.assertTrue(target);self.assertEqual(fields(source),fields(target),(language,source))

    def test_french_is_an_identity_translation(self):
        for text in('Réglages','Noir','Code 114 non interprété','USB DIRECT OBLIGATOIRE',RISK_NOTICE):self.assertEqual(tr(text),text)

    def test_dynamic_status_and_old_notification_are_translated(self):
        set_language('en')
        self.assertEqual(tr('Niveau signalé : 42 %'),'Reported level: 42 %')
        self.assertEqual(tr('Réserve atteinte : Noir'),'Reserve reached: Black')
        self.assertEqual(tr('104 pages · 44 couleur · 60 noir et blanc'),'104 pages · 44 colour · 60 black and white')
        set_language('es')
        self.assertEqual(tr('Code 114 non interprété'),'Código 114 sin interpretar')
        self.assertEqual(tr('Niveau estimé : 16 %. Consulter la réserve dans OpenInk.'),'Nivel estimado: 16 %. Consulta la reserva en OpenInk.')

    def test_unknown_data_and_identifiers_are_not_rewritten(self):
        set_language('es')
        for text in('Epson_XP_2200-54','IU05P2','TEST220001','604XL','http://printer.local/ipp/print','78 %'):
            self.assertEqual(tr(text),text)

    def test_saved_language_reader_does_not_create_a_database(self):
        self.assertEqual(saved_language(self.path),'auto');self.assertFalse(self.path.exists())
        store=Store(self.path)
        try:store.set_setting('language','es')
        finally:store.close()
        self.assertEqual(saved_language(self.path),'es')

    def test_invalid_preference_is_rejected_and_existing_value_preserved(self):
        store=Store(self.path)
        try:
            store.set_setting('language','fr')
            with self.assertRaises(ValueError):store.set_setting('language','de')
            self.assertEqual(store.setting('language'),'fr')
        finally:store.close()

    def test_automatic_language_selection(self):
        with patch.dict(os.environ,{'LANGUAGE':'es_ES:en','LC_ALL':'','LC_MESSAGES':'','LANG':'fr_FR.UTF-8'}):
            self.assertEqual(resolve_language('auto'),'es')
        self.assertEqual(resolve_language('en'),'en');self.assertEqual(resolve_language('not-a-language'),'fr')

    def test_each_language_has_its_own_test_page(self):
        paths=[]
        for language in('fr','en','es'):
            set_language(language);paths.append(test_page())
            self.assertTrue(test_page().read_bytes().startswith(b'%PDF-'))
        self.assertEqual(len(set(paths)),3)

    def test_demo_option_is_removed_before_any_launch(self):
        from inkora.__main__ import main
        with patch.object(sys,'argv',['openink','--database',str(self.path),'--demo']), \
             patch('inkora.__main__.tk.Tk')as window,patch('inkora.service.ensure_agent')as agent,redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit)as caught:main()
            self.assertEqual(caught.exception.code,2);window.assert_not_called();agent.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_help_is_localized_and_contains_no_demo_option(self):
        from inkora.__main__ import main
        for language,expected in[('en','Interface language'),('es','Idioma de la interfaz')]:
            output=StringIO()
            with patch.object(sys,'argv',['openink','--database',str(self.path),'--lang',language,'--help']),redirect_stdout(output):
                with self.assertRaises(SystemExit)as caught:main()
            self.assertEqual(caught.exception.code,0)
            self.assertIn(expected,output.getvalue());self.assertNotIn('--demo',output.getvalue())

    def test_critical_flash_warning_has_full_translations(self):
        for language,word in[('en','risks'),('es','riesgos')]:
            set_language(language);self.assertIn(word,tr(RISK_NOTICE))
            self.assertNotEqual(tr('J’ai lu l’avertissement et j’accepte les risques du flash.'),'J’ai lu l’avertissement et j’accepte les risques du flash.')
            self.assertIn('USB',tr('L’Epson est reliée directement par câble USB (obligatoire).'))

    def test_notification_fallback_translates_only_at_delivery(self):
        from inkora.notifications import send_notification
        for language in('en','es'):
            set_language(language)
            with patch('inkora.notifications.shutil.which',return_value='/test/notify-send'), \
                 patch('inkora.notifications.subprocess.run',return_value=SimpleNamespace(returncode=0))as run:
                self.assertTrue(send_notification('Réserve atteinte : Noir','Niveau estimé : 16 %. Consulter la réserve dans OpenInk.'))
                command=run.call_args.args[0]
                self.assertEqual(command[-2],tr('Réserve atteinte : Noir'))
                self.assertEqual(command[-1],tr('Niveau estimé : 16 %. Consulter la réserve dans OpenInk.'))


if __name__=='__main__':unittest.main()
