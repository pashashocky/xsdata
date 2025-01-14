import sys
import tempfile
import warnings
from pathlib import Path
from unittest import TestCase

from xsdata import __version__
from xsdata.exceptions import GeneratorConfigError
from xsdata.exceptions import ParserError
from xsdata.models.config import GeneratorConfig
from xsdata.models.config import OutputFormat


class GeneratorConfigTests(TestCase):
    def setUp(self) -> None:
        self.maxDiff = None

    def test_create(self):
        file_path = Path(tempfile.mktemp())
        obj = GeneratorConfig.create()
        with file_path.open("w") as fp:
            obj.write(fp, obj)

        expected = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<Config xmlns="http://pypi.org/project/xsdata" version="{__version__}">\n'
            '  <Output maxLineLength="79">\n'
            "    <Package>generated</Package>\n"
            '    <Format repr="true" eq="true" order="false" unsafeHash="false"'
            ' frozen="false" slots="false" kwOnly="false">dataclasses</Format>\n'
            "    <Structure>filenames</Structure>\n"
            "    <DocstringStyle>reStructuredText</DocstringStyle>\n"
            "    <RelativeImports>false</RelativeImports>\n"
            "    <CompoundFields>false</CompoundFields>\n"
            "  </Output>\n"
            "  <Conventions>\n"
            '    <ClassName case="pascalCase" safePrefix="type"/>\n'
            '    <FieldName case="snakeCase" safePrefix="value"/>\n'
            '    <ConstantName case="screamingSnakeCase" safePrefix="value"/>\n'
            '    <ModuleName case="snakeCase" safePrefix="mod"/>\n'
            '    <PackageName case="snakeCase" safePrefix="pkg"/>\n'
            "  </Conventions>\n"
            "  <Aliases>\n"
            '    <ClassName source="fooType" target="Foo"/>\n'
            '    <ClassName source="ABCSomething" target="ABCSomething"/>\n'
            '    <FieldName source="ChangeofGauge" target="change_of_gauge"/>\n'
            '    <PackageName source="http://www.w3.org/1999/xhtml" target="xtml"/>\n'
            '    <ModuleName source="2010.1" target="2020a"/>\n'
            "  </Aliases>\n"
            "</Config>\n"
        )
        self.assertEqual(expected, file_path.read_text())
        file_path.unlink()

    def test_read(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Config xmlns="http://pypi.org/project/xsdata" version="20.8">\n'
            '  <Output maxLineLength="79">\n'
            "    <Package>foo.bar</Package>\n"
            "  </Output>\n"
            "  <Conventions>\n"
            '    <ClassName case="pascalCase" safePrefix="type"/>\n'
            "  </Conventions>\n"
            "  <Aliases/>\n"
            "</Config>\n"
        )
        file_path = Path(tempfile.mktemp())
        file_path.write_text(existing, encoding="utf-8")
        config = GeneratorConfig.read(file_path)
        with file_path.open("w") as fp:
            GeneratorConfig.write(fp, config)

        expected = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<Config xmlns="http://pypi.org/project/xsdata" version="{__version__}">\n'
            '  <Output maxLineLength="79">\n'
            "    <Package>foo.bar</Package>\n"
            '    <Format repr="true" eq="true" order="false" unsafeHash="false"'
            ' frozen="false" slots="false" kwOnly="false">dataclasses</Format>\n'
            "    <Structure>filenames</Structure>\n"
            "    <DocstringStyle>reStructuredText</DocstringStyle>\n"
            "    <RelativeImports>false</RelativeImports>\n"
            "    <CompoundFields>false</CompoundFields>\n"
            "  </Output>\n"
            "  <Conventions>\n"
            '    <ClassName case="pascalCase" safePrefix="type"/>\n'
            '    <FieldName case="snakeCase" safePrefix="value"/>\n'
            '    <ConstantName case="screamingSnakeCase" safePrefix="value"/>\n'
            '    <ModuleName case="snakeCase" safePrefix="mod"/>\n'
            '    <PackageName case="snakeCase" safePrefix="pkg"/>\n'
            "  </Conventions>\n"
            "  <Aliases/>\n"
            "</Config>\n"
        )
        self.assertEqual(expected, file_path.read_text())

    def test_read_with_wrong_value(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<Config xmlns="http://pypi.org/project/xsdata" version="21.7">\n'
            '  <Output maxLineLength="79">\n'
            "    <Structure>unknown</Structure>\n"
            "  </Output>\n"
            "</Config>\n"
        )
        file_path = Path(tempfile.mktemp())
        file_path.write_text(existing, encoding="utf-8")
        with self.assertRaises(ParserError):
            GeneratorConfig.read(file_path)

    def test_format_with_invalid_state(self):

        with self.assertRaises(GeneratorConfigError) as cm:
            OutputFormat(eq=False, order=True)

        self.assertEqual("eq must be true if order is true", str(cm.exception))

    def test_format_slots_requires_310(self):
        if sys.version_info < (3, 10):
            self.assertTrue(OutputFormat(slots=True, value="attrs").slots)

            with warnings.catch_warnings(record=True) as w:
                self.assertFalse(OutputFormat(slots=True).slots)

            self.assertEqual(
                "slots requires python >= 3.10, reverting...", str(w[-1].message)
            )

        else:
            self.assertIsNotNone(OutputFormat(slots=True))

    def test_format_kw_only_requires_310(self):
        if sys.version_info < (3, 10):
            self.assertTrue(OutputFormat(kw_only=True, value="attrs").kw_only)

            with warnings.catch_warnings(record=True) as w:
                self.assertFalse(OutputFormat(kw_only=True).kw_only)

            self.assertEqual(
                "kw_only requires python >= 3.10, reverting...", str(w[-1].message)
            )

        else:
            self.assertIsNotNone(OutputFormat(kw_only=True))
