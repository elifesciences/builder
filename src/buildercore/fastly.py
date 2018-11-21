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

    def insert(self, section, hook, statements):
        section_start = self._find_section_start(section)
        lines = list(self._lines)
        if hook == 'after':
            lines[section_start + 1:section_start + 1] = ['  %s' % s for s in statements]
            lines.insert(section_start + 1, '')
        if hook == 'before':
            lines.insert(section_start, '')
            lines[section_start:section_start] = ['  %s' % s for s in statements]
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

class FastlyVCLInclusion(namedtuple('FastlyVCLInclusion', ['name', 'type', 'hook'])):
    def insert_include(self, main_vcl):
        return main_vcl.insert(
            self.type,
            self.hook,
            [
                '// BEGIN builder %s' % self.name,
                'include "%s"' % self.name,
                '// END builder %s' % self.name,
            ]
        )


class FastlyVCLSnippet(namedtuple('FastlyVCLSnippet', ['name', 'content', 'type', 'hook'])):
    """VCL snippets that can be used to augment the default VCL

    Due to Terraform limitations we are unable to pass these directly to the Fastly API, and have to build a whole VCL ourselves.

    Terminology for fields comes from https://docs.fastly.com/api/config#snippet"""

    def as_inclusion(self):
        return FastlyVCLInclusion(self.name, self.type, self.hook)

class FastlyVCLTemplate(namedtuple('FastlyVCLTemplate', ['name', 'content', 'type', 'hook'])):
    def as_inclusion(self, name):
        return FastlyVCLInclusion(name, self.type, self.hook)

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
    'original-host': FastlyVCLSnippet(
        name='original-host',
        content=_read_vcl_file('original-host.vcl'),
        type='recv',
        hook='before'
    ),
    'gzip-by-content-type-suffix': FastlyVCLSnippet(
        name='gzip-by-content-type-suffix',
        content=_read_vcl_file('gzip-by-content-type-suffix.vcl'),
        type='fetch',
        hook='after'
    ),
    'office-webdav-200': FastlyVCLSnippet(
        name='office-webdav-200',
        content=_read_vcl_file('office-webdav-200.vcl'),
        type='recv',
        hook='after'
    ),
    'ping-status': FastlyVCLSnippet(
        name='ping-status',
        content=_read_vcl_file('ping-status.vcl'),
        type='recv',
        hook='after'
    ),
    'strip-non-journal-cookies': FastlyVCLSnippet(
        name='strip-non-journal-cookies',
        content=_read_vcl_file('strip-non-journal-cookies.vcl'),
        type='recv',
        hook='after'
    ),
    'journal-google-scholar': FastlyVCLSnippet(
        name='journal-google-scholar',
        content=_read_vcl_file('journal-google-scholar.vcl'),
        type='recv',
        hook='after'
    ),
    'journal-google-scholar-vary': FastlyVCLSnippet(
        name='journal-google-scholar-vary',
        content=_read_vcl_file('journal-google-scholar-vary.vcl'),
        type='deliver',
        hook='after'
    ),
}

VCL_TEMPLATES = {
    'error-page': FastlyVCLTemplate(
        name='error-page',
        content=_read_vcl_file('error-page.vcl.tpl'),
        type='error',
        hook='after'
    ),
    'journal-submit': FastlyVCLSnippet(
        name='journal-submit',
        content=_read_vcl_file('journal-submit.vcl.tpl'),
        type='recv',
        hook='before'
    ),
}
