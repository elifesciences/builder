"""models Fastly API concepts

No dependencies on Terraform should be in this module"""

from collections import namedtuple
import re
import os

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

    def __repr__(self):
        return "FastlyVCL(%s)" % repr(self._lines)

    def insert(self, section, statements):
        section_start = self._find_section_start(section)
        lines = list(self._lines)
        lines[section_start + 1:section_start + 1] = ['  %s' % s for s in statements]
        lines.insert(section_start + 1, '')
        return FastlyVCL(lines)

    def _find_section_start(self, section):
        lookup = r"^( *)#FASTLY %s" % section
        section_start = None
        for i, line in enumerate(self._lines):
            m = re.match(lookup, line)
            if m:
                section_start = i
                break
        if section_start is None:
            raise FastlyCustomVCLGenerationError("Cannot match %s into main VCL template:\n\n%s" % (lookup, str(self)))
        return section_start

class FastlyVCLSnippet(namedtuple('FastlyVCLSnippet', ['name', 'content', 'type'])):
    """VCL snippets that can be used to augment the default VCL

    Due to Terraform limitations we are unable to pass these directly to the Fastly API, and have to build a whole VCL ourselves.

    Terminology for fields comes from https://docs.fastly.com/api/config#snippet"""

    def insert_include(self, main_vcl):
        return main_vcl.insert(
            self.type,
            [
                '// BEGIN builder %s' % self.name,
                'include "%s"' % self.name,
                '// END builder %s' % self.name,
            ]
        )

class FastlyCustomVCLGenerationError(Exception):
    pass

_directory = os.path.join(os.path.dirname(__file__), 'fastly', 'vcl')
def _read_vcl_file(name):
    with open(os.path.join(_directory, name)) as fp:
        return fp.read()

# taken from https://docs.fastly.com/guides/vcl/mixing-and-matching-fastly-vcl-with-custom-vcl#fastlys-vcl-boilerplate
# Fastly expands #FASTLY macros into generated VCL
MAIN_VCL_TEMPLATE = FastlyVCL.from_string(_read_vcl_file('main.vcl'))

VCL_SNIPPETS = {
    'gzip-by-content-type-suffix': FastlyVCLSnippet(
        name='gzip-by-content-type-suffix',
        content=_read_vcl_file('gzip-by-content-type-suffix.vcl'),
        type='fetch'
    ),
}
