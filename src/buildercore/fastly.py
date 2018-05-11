"""models Fastly API concepts

No dependencies on Terraform should be in this module"""

from collections import namedtuple
import re

class FastlyVCL:
    @classmethod
    def from_string(cls, content):
        return cls(content.splitlines())

    def __init__(self, lines):
        self._lines = lines

    def __eq__(self, another):
        return self._lines == another._lines

    def __str__(self):
        return "\n".join(self._lines)

    def insert(self, section, statement):
        # TODO: if we remove indentation altogether from all lines, this will become a single return value
        section_start, indentation = self._find_section_start(section)
        lines = list(self._lines)
        lines.insert(section_start + 1, '')
        lines.insert(
            section_start + 1,
            '%s  %s' % (indentation, statement)
        )
        return FastlyVCL(lines)

    def _find_section_start(self, section):
        lookup = r"(?P<indentation> +)sub vcl_%s {" % section
        section_start = None
        for i, line in enumerate(self._lines):
            m = re.match(lookup, line)
            if m:
                section_start = i
                break
        if section_start is None:
            raise FastlyCustomVCLGenerationError("Cannot match %s into main VCL template:\n\n%s" % (lookup, str(self)))
        return section_start, m.group(1)

"""VCL snippets that can be used to augment the default VCL

Due to Terraform limitations we are unable to pass these directly to the Fastly API, and have to build a whole VCL ourselves.

Terminology for fields comes from https://docs.fastly.com/api/config#snippet"""
class FastlyCustomVCLSnippet(namedtuple('FastlyCustomVCLSnippet', ['name', 'content', 'type'])):
    def insert_include(self, main_vcl):
        # TODO: pass more lines in, and add a comment on where this is coming from
        return main_vcl.insert(self.type, 'include "%s"' % self.name)

class FastlyCustomVCLGenerationError(Exception):
    pass
