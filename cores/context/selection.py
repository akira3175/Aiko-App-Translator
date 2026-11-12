"""Select translated glossary names relevant to current chapters."""

import os

from cores.context.glossary import filter_glossary
from cores.storage.project import load_context
from cores.pronouns import (
    NameResolver,
    _name_matches_glossary,
    load_character_roster,
    load_pronouns,
)
from cores.pronouns.normalize import default_characters_file


def find_glossary_targets(file_path, raw_text="", pronouns_file=None):
    if not os.path.exists(file_path):
        return []
    context = load_context(os.path.dirname(file_path))
    targets = []
    for line in filter_glossary(context.get("glossary", ""), raw_text).splitlines():
        _source, separator, target = line.partition("=")
        target = target.strip()
        if separator and target and target not in targets:
            targets.append(target)

    if not pronouns_file:
        return targets
    memory = load_pronouns(pronouns_file)
    resolver = NameResolver(
        load_character_roster(default_characters_file(pronouns_file))
    )
    character_names = []
    # A known character may not have pronoun history yet. Keep its glossary
    # name so context selection can distinguish that from unknown characters.
    for character in resolver.names():
        character_names.extend(resolver.aliases(character))
    for data in memory.values():
        if not isinstance(data, dict):
            continue
        for character in data.get("characters", []):
            if character:
                character_names.extend(resolver.aliases(str(character)))
    return [
        target
        for target in targets
        if any(_name_matches_glossary(character, target) for character in character_names)
    ]
