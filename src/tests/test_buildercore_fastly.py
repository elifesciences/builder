from buildercore.terraform import fastly
from . import base

class TestFastlyCustomVCL(base.BaseCase):
    def test_includes_a_reference_to_itself_in_template(self):
        snippet = fastly.FastlyVCLSnippet(
            name='do-some-magic',
            content='...',
            type='fetch'
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

    def test_fails_if_no_section_can_be_found(self):
        snippet = fastly.FastlyVCLSnippet(
            name='do-some-magic',
            content='...',
            type='hit'
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
