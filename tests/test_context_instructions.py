import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.context.prompts import DEFAULT_CONTEXT_INSTRUCTIONS, build_glossary_prompt
from cores.context.workflow import run_context_generation
from cores.storage.project import load_context, save_context
from services.context.service import ContextService


class ContextInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('A','B'):
            (self.root/name/'raw').mkdir(parents=True)
            for index in range(2):
                (self.root/name/'raw'/f'v1_c{index}_s1.md').write_text(f'# Title {index}\n\nBody {index}',encoding='utf-8')
        self.service=ContextService(lambda name:self.root/name)

    def test_saved_instructions_are_project_scoped_and_resettable(self):
        fields={'index':0,'glossary':'Name = Ten','context_instructions':'Only names'}
        self.service.save('A',{'context_fields':fields})
        self.assertEqual('Only names',self.service.data('A')['context_instructions'])
        self.assertEqual(DEFAULT_CONTEXT_INSTRUCTIONS,self.service.data('B')['context_instructions'])
        self.service.save('A',{'context_fields':{**fields,'context_instructions':DEFAULT_CONTEXT_INSTRUCTIONS}})
        self.assertTrue((self.root/'A'/'context.json.bak').exists())
        self.assertEqual(DEFAULT_CONTEXT_INSTRUCTIONS,self.service.data('A')['context_instructions'])
        with self.assertRaises(ValueError):
            self.service.save('A',{'context_fields':{**fields,'context_instructions':'x'*20001}})

    def test_preview_uses_unsaved_draft_next_batch_and_does_not_write(self):
        data=self.service.preview_prompt('A',{'index':1,'batch_size':1,'context_instructions':'Draft rule','glossary':'Old = Existing'})
        expected=build_glossary_prompt([{'title':'Title 1','content':'Body 1'}],'Old = Existing','Draft rule')
        self.assertEqual(expected,data['prompt'])
        self.assertEqual(['v1_c1_s1.md'],data['chapters'])
        self.assertFalse((self.root/'A'/'context.json').exists())
        self.assertIn('###START###',data['prompt'])
        self.assertIn('###END###',data['prompt'])
        self.assertEqual('',self.service.preview_prompt('A',{'index':2})['prompt'])

    def test_workflow_reloads_instructions_for_each_batch(self):
        project=self.root/'A'
        save_context(project,{'index':0,'glossary':'','context_instructions':'First rule'})
        seen=[]
        def generate(batch,old,instructions=None):
            seen.append(instructions)
            current=load_context(project)
            current['context_instructions']='Next rule'
            save_context(project,current)
            return '###START###\nName = Ten\n###END###'
        with patch('cores.context.workflow.time.sleep'):
            run_context_generation(engine_name='test',setup_browser=None,close_browser=None,generate_glossary=generate,raw_dir=project/'raw',context_file=project/'context.json',batch_size=1)
        self.assertEqual(['First rule','Next rule'],seen)
        self.assertEqual('Next rule',load_context(project)['context_instructions'])
