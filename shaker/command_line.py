import argparse
import sys
import shaker.libs.logger

import salt_shaker


class ShakerCommandLine(object):

    def run(self, cli_args):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        common_args = argparse.ArgumentParser(add_help=False)
        common_args.add_argument('--root_dir', default='.', help="Working path to operate under")
        common_args.add_argument('--verbose', '-v', action='store_true', help="Enable verbose logging")
        common_args.add_argument('--debug', '-d', action='store_true', help="Enable debug logging")
        common_args.add_argument('--simulate', '-s', action='store_true', help="Only simulate the command, do not commit any changes")
       
        parser_install = subparsers.add_parser('install',
                                               help=("Install formulas and requirements"),
                                               parents=[common_args])
        parser_install.set_defaults(overwrite=True)
        parser_install.set_defaults(func=self.shake)
        parser_shake = subparsers.add_parser('shake', help=("(Alias for install) "
                                             "Install formulas and requirements"),
                                             parents=[common_args])
        parser_shake.set_defaults(overwrite=True)
        parser_shake.set_defaults(func=self.shake)

        parser_refresh = subparsers.add_parser('refresh',
                                               help=("Refresh formulas and requirements"),
                                               parents=[common_args])
        parser_refresh.set_defaults(overwrite=False)
        parser_refresh.set_defaults(func=self.shake)
        parser_update = subparsers.add_parser('update', help=("(Alias for refresh) "
                                                              "Refresh formulas and requirements"),
                                              parents=[common_args])
        parser_update.set_defaults(overwrite=False)
        parser_update.set_defaults(func=self.shake)
        

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
