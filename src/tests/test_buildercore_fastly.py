from buildercore.terraform import fastly
from . import base

class TestFastlyCustomVCL(base.BaseCase):
    def test_inserts_snippets_through_include_statements(self):
        snippet = fastly.FastlyVCLInclusion(
            name='do-some-magic',
            type='fetch',
            hook='after'
        )
        original_main_vcl = fastly.FastlyVCL.from_string("""
sub vcl_fetch {
  #FASTLY fetch

  if (...) {
    do_something_else()
  }
}
""")
        expected_main_vcl = fastly.FastlyVCL.from_string("""
sub vcl_fetch {
  #FASTLY fetch

  // BEGIN builder do-some-magic
  include "do-some-magic"
  // END builder do-some-magic

  if (...) {
    do_something_else()
  }
}
""")
        self.assertEqual(
            snippet.insert_include(original_main_vcl),
            expected_main_vcl
        )

    def test_snippets_can_be_included_even_before_fastly_macros(self):
        snippet = fastly.FastlyVCLInclusion(
            name='do-some-magic',
            type='fetch',
            hook='before'
        )
        original_main_vcl = fastly.FastlyVCL.from_string("""
sub vcl_fetch {
  #FASTLY fetch

  if (...) {
    do_something_else()
  }
}
""")
        expected_main_vcl = fastly.FastlyVCL.from_string("""
sub vcl_fetch {
  // BEGIN builder do-some-magic
  include "do-some-magic"
  // END builder do-some-magic

  #FASTLY fetch

  if (...) {
    do_something_else()
  }
}
""")
        self.assertEqual(
            snippet.insert_include(original_main_vcl),
            expected_main_vcl
        )

    def test_stops_generation_if_an_inclusion_section_cannot_be_found(self):
        snippet = fastly.FastlyVCLInclusion(
            name='do-some-magic',
            type='hit',
            hook='after'
        )
        original_main_vcl = fastly.FastlyVCL.from_string("""
        sub vcl_fetch {
          ...
        }
        """)
        self.assertRaises(
            fastly.FastlyCustomVCLGenerationError,
            lambda: snippet.insert_include(original_main_vcl),
        )
