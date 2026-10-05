import unittest

from anti_slop_core import cli


class CliParserP0Tests(unittest.TestCase):
    def test_public_parser_accepts_only_p0_commands(self):
        parser = cli.build_parser()

        self.assertEqual(parser.parse_args(["diagnose", "--spec", "/tmp/spec.json"]).command, "diagnose")
        self.assertEqual(
            parser.parse_args(["validate-findings", "--manifest", "/tmp/manifest.json", "--findings", "/tmp/findings.json"]).command,
            "validate-findings",
        )
        for command in ("refactor", "repair-slop"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    parser.parse_args([command])


if __name__ == "__main__":
    unittest.main()
