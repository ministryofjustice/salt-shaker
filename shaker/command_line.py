import argparse
import sys

import salt_shaker


class ShakerCommandLine(object):

    def run(self, cli_args):
        parser = argparse.ArgumentParser(add_help=True)
        subparsers = parser.add_subparsers()

        parser.add_argument('--root_dir',
                            default='.',
                            help="Working path to operate under")
        parser.add_argument('--verbose',
                            action='store_true',
                            help="Enable verbose logging")
        parser.add_argument('--debug',
                            action='store_true',
                            help="Enable debug logging")
        parser.add_argument('--simulate',
                            '-s',
                            action='store_true',
                            help="Only simulate the command, do not commit any changes")
        parser.add_argument('--enable-remote-check',
                            action='store_true',
                            help="Enable remote checks when installing pinned versions")

        parser_install = subparsers.add_parser('install',
                                               help=("Install formulas and requirements from metadata.yml, "
                                                     "recursively resolving remote dependencies"),
                                               )
        parser_install.set_defaults(pinned=False)
        parser_install.set_defaults(func=self.shake)

        parser_refresh = subparsers.add_parser('install-pinned-versions',
                                               help=("Install pinned versions of formulas "
                                                     "using formula-requirements.txt"))
        parser_refresh.set_defaults(pinned=True)
        parser_refresh.set_defaults(func=self.shake)

        parser_check = subparsers.add_parser('check',
                                             help=("Check versions of formulas against an update"))
        parser_check.set_defaults(check_requirements=True)
        parser_check.set_defaults(func=self.shake)

        args_ns = parser.parse_args(args=self.back_compat_args_fix(cli_args))
        # Convert the args as Namespace to dict a so we can pass it as kwargs to a function
        args = vars(args_ns)

        return args.pop('func')(**args)

    def back_compat_args_fix(self, cli_args):
        args = []
        for arg in cli_args:
            if arg.startswith("root_") and "=" in arg:
                arg = "--" + arg
            args.append(arg)

        return args

    def shake(self, **kwargs):
        salt_shaker.shaker(**kwargs)


if __name__ == '__main__':
    ShakerCommandLine().run(sys.argv)
