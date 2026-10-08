from pathlib import Path

import pytest


def test_local_skills_have_only_allowed_tools():
    from agents import load_skill
    for module in ('trip', 'decision', 'planning'):
        skill = load_skill(Path('src') / module / 'skills.yaml')
        assert skill.name == module
        assert skill.workflow and skill.tools
        assert all(tool.name.startswith(module + '.') for tool in skill.tools)
        assert all('corpus' not in tool.name for tool in skill.tools)


@pytest.mark.parametrize('body', [
    'name: trip\nworkflow: [compile]\ntools: [{name: corpus.write, access: write}]',
    'name: trip\nworkflow: [compile]\ntools: [{name: trip.compile, access: execute}]',
    'name: trip\nworkflow: []\ntools: []',
    'name: trip\nworkflow: [compile]\ntools: [{name: decision.compare, access: read}]',
    'name: trip\nworkflow: [compile]\ntools: [{name: trip.compile, access: read}]\nexecute: os.system',
])
def test_skill_rejects_unknown_or_unsafe_declarations(tmp_path, body):
    from agents import load_skill
    path = tmp_path / 'skills.yaml'
    path.write_text(body)
    with pytest.raises(ValueError):
        load_skill(path)
