import cmd
import sys
import logging

import salt_shaker


logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ShakerCommandLine(cmd.Cmd):
    def shake(self, line, force=False):
        if line and '=' not in line:
            print "syntax error."
            return False
        parms = dict([x.split('=') for x in line.split(' ')])\
            if isinstance(line, basestring) else {}
        if force in parms and parms['force'].lower() != 'false':
            parms['force'] = True
        salt_shaker.shaker(**parms)

    def do_shake(self, line):
        self.shake(line)

    def do_update(self, line):
        self.shake(line, force=True)

    def default(self, line):
        return self.do_help(line)

    def help_shake(self):
        msg = '''Start from root formula and download all prerequisites.\n'''\
        '''Parameters:\n'''\
        '''\troot_dir=<path> path to working directory. Default: '.'\n'''\
        '''\tforce=<True/False> recalculate dependencies if True'''
        print msg

    def help_update(self):
        msg = '''Convenience command equal to "shaker force=True" '''
        print msg


    def run(self, argv):
        if len(argv) > 1:
            self.onecmd(' '.join(argv[1:]))
        else:
            self.do_help('')


if __name__ == '__main__':
    ShakerCommandLine().run(sys.argv)
