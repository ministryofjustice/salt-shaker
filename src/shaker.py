import cmd
import sys

import salt_shaker


class ShakerCommandLine(cmd.Cmd):
    def do_shake(self, line):
        if '=' not in line:
            print "syntax error."
            return False
        parms = dict([x.split('=') for x in line.split(' ')])
        salt_shaker.shaker(**parms)

    def default(self, line):
        return self.do_help(line)

    def help_shake(self):
        print "Hello world"

if __name__ == '__main__':
    if len(sys.argv) > 1:
        ShakerCommandLine().onecmd(' '.join(sys.argv[1:]))
    else:
        print 'help'
