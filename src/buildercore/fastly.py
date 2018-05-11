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
class FastlyVCLSnippet(namedtuple('FastlyVCLSnippet', ['name', 'content', 'type'])):
    def insert_include(self, main_vcl):
        # TODO: pass more lines in, and add a comment on where this is coming from
        return main_vcl.insert(self.type, 'include "%s"' % self.name)

class FastlyCustomVCLGenerationError(Exception):
    pass

# taken from https://docs.fastly.com/guides/vcl/mixing-and-matching-fastly-vcl-with-custom-vcl#fastlys-vcl-boilerplate
# Fastly expands #FASTLY macros into generated VCL
# TODO: extract into file
MAIN_VCL_TEMPLATE = FastlyVCL.from_string("""
    sub vcl_recv {
      #FASTLY recv

      if (req.request != "HEAD" && req.request != "GET" && req.request != "FASTLYPURGE") {
        return(pass);
      }

      return(lookup);
    }

    sub vcl_fetch {
      #FASTLY fetch

      if ((beresp.status == 500 || beresp.status == 503) && req.restarts < 1 && (req.request == "GET" || req.request == "HEAD")) {
        restart;
      }

      if (req.restarts > 0) {
        set beresp.http.Fastly-Restarts = req.restarts;
      }

      if (beresp.http.Set-Cookie) {
        set req.http.Fastly-Cachetype = "SETCOOKIE";
        return(pass);
      }

      if (beresp.http.Cache-Control ~ "private") {
        set req.http.Fastly-Cachetype = "PRIVATE";
        return(pass);
      }

      if (beresp.status == 500 || beresp.status == 503) {
        set req.http.Fastly-Cachetype = "ERROR";
        set beresp.ttl = 1s;
        set beresp.grace = 5s;
        return(deliver);
      }

      if (beresp.http.Expires || beresp.http.Surrogate-Control ~ "max-age" || beresp.http.Cache-Control ~ "(s-maxage|max-age)") {
        # keep the ttl here
      } else {
        # apply the default ttl
        set beresp.ttl = 3600s;
      }

      return(deliver);
    }

    sub vcl_hit {
      #FASTLY hit

      if (!obj.cacheable) {
        return(pass);
      }
      return(deliver);
    }

    sub vcl_miss {
      #FASTLY miss
      return(fetch);
    }

    sub vcl_deliver {
      #FASTLY deliver
      return(deliver);
    }

    sub vcl_error {
      #FASTLY error
    }

    sub vcl_pass {
      #FASTLY pass
    }

    sub vcl_log {
      #FASTLY log
    }""")

VCL_SNIPPETS = {
    'gzip-by-regex': FastlyVCLSnippet(
        name='gzip-by-regex',
        content="""
        if ((beresp.status == 200 || beresp.status == 404) && (beresp.http.content-type ~ "(\+json)\s*($|;)" || req.url ~ "\.(css|js|html|eot|ico|otf|ttf|json|svg)($|\?)" ) ) {
          # always set vary to make sure uncompressed versions dont always win
          if (!beresp.http.Vary ~ "Accept-Encoding") {
            if (beresp.http.Vary) {
              set beresp.http.Vary = beresp.http.Vary ", Accept-Encoding";
            } else {
              set beresp.http.Vary = "Accept-Encoding";
            }
          }
          if (req.http.Accept-Encoding == "gzip") {
            set beresp.gzip = true;
          }
        }
        """,
        type='fetch'
    ),
}
