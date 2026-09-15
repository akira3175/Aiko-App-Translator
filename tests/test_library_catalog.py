import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.library import LibraryService
from services.library.catalog import catalog, hidden_projects, set_hidden
from tests import test_project_routes as route_helpers

_Handler = route_helpers._Handler


class LibraryCatalogTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        for name in ('Alpha', 'Beta'):
            (self.root/name/'raw').mkdir(parents=True)
            (self.root/name/'translated').mkdir()
            (self.root/name/'raw'/'v1_c1_s1.md').write_text('# One\n\nBody', encoding='utf-8')
        (self.root/'Alpha'/'translated'/'v1_c1_s1.md').write_text('# Done', encoding='utf-8')
        self.service=LibraryService(self.root)
        self.routes=route_helpers.ProjectRouteTests()._routes(self.root, projects=self.service.projects, safe_project=self.service.safe_project)

    def test_hide_persists_without_removing_projects_or_chapters(self):
        set_hidden(self.root,'Alpha',True)
        self.assertEqual({'Alpha'}, hidden_projects(self.root))
        self.assertEqual(['Alpha','Beta'],self.service.projects())
        items=catalog(self.root)
        self.assertEqual({'name':'Alpha','hidden':True,'total':1,'translated':1},items[0])
        self.assertTrue((self.root/'Alpha'/'raw'/'v1_c1_s1.md').exists())
        set_hidden(self.root,'Beta',True)
        set_hidden(self.root,'Alpha',False)
        self.assertEqual({'Beta'},hidden_projects(self.root))

    def test_rejects_missing_project_traversal_and_non_boolean(self):
        for name,hidden in [('Missing',True),('../escape',True),('Alpha','false')]:
            with self.subTest(name=name,hidden=hidden),self.assertRaises(ValueError):
                set_hidden(self.root,name,hidden)
        self.assertFalse((self.root/'.library.json').exists())

    def test_api_lists_all_names_and_separate_hidden_state(self):
        handler=_Handler({'hidden':True})
        self.routes.handle_post(handler,'/api/library/visibility',{'project':['Alpha']})
        self.assertEqual(200,handler.responses[-1][0])
        self.routes.handle_get(handler,'/api/projects',{})
        self.assertEqual({'items':['Alpha','Beta'],'hidden':['Alpha']},handler.responses[-1][1])
        handler.is_loopback=lambda:True
        self.routes.handle_get(handler,'/api/library',{})
        self.assertEqual(2,len(handler.responses[-1][1]['items']))

    def test_open_folder_uses_validated_project_path(self):
        handler=_Handler()
        handler.is_loopback=lambda:True
        with patch('server.routes.projects.os.startfile',create=True) as start:
            self.routes.handle_post(handler,'/api/library/open-folder',{'project':['Alpha']})
            start.assert_called_once_with(str((self.root/'Alpha').resolve()))
            self.assertEqual({'ok':True},handler.responses[-1][1])
            start.reset_mock()
            self.routes.handle_post(handler,'/api/library/open-folder',{'project':['../escape']})
            start.assert_not_called()
            self.assertEqual(400,handler.responses[-1][0])

    def test_remote_browser_cannot_open_folder_on_host(self):
        handler=_Handler()
        handler.is_loopback=lambda:False
        with patch('server.routes.projects.os.startfile',create=True) as start:
            self.routes.handle_post(handler,'/api/library/open-folder',{'project':['Alpha']})
            start.assert_not_called()
            self.assertEqual(403,handler.responses[-1][0])
