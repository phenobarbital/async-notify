"""utils.

    Useful functions for Notify.
"""
class SafeDict(dict):
    """
    SafeDict.

    Allow to using partial format strings

    """

    def __missing__(self, key):
        """Missing method for SafeDict."""
        return '{' + key + '}'


class colors:
    """
    Colors class.

       reset all colors with colors.reset;
       Use as colors.subclass.colorname.
    i.e. colors.fg.red or colors.fg.greenalso, the generic bold, disable,
    underline, reverse, strike through,
    and invisible work with the main class i.e. colors.bold
    """

    reset = '\033[0m'
    bold = '\033[01m'
    disable = '\033[02m'
    underline = '\033[04m'
    reverse = '\033[07m'
    strikethrough = '\033[09m'
    invisible = '\033[08m'

    class fg:
        """
        colors.fg.

        Foreground Color subClass
        """

        black = '\033[30m'
        red = '\033[31m'
        green = '\033[32m'
        orange = '\033[33m'
        blue = '\033[34m'
        purple = '\033[35m'
        cyan = '\033[36m'
        lightgrey = '\033[37m'
        darkgrey = '\033[90m'
        lightred = '\033[91m'
        lightgreen = '\033[92m'
        yellow = '\033[93m'
        lightblue = '\033[94m'
        pink = '\033[95m'
        lightcyan = '\033[96m'


class Msg(object):
    def __init__(self, message: str = "", level: str = "INFO"):
        if level == "INFO" or level == "info":
            coloring = colors.bold + colors.fg.green
        elif level == "DEBUG" or level == "debug":
            coloring = colors.fg.lightblue
        elif level == "WARN" or level == "warning":
            coloring = colors.bold + colors.fg.yellow
        elif self.level == "ERROR":
            coloring = colors.fg.lightred
        elif self.level == "CRITICAL":
            coloring = colors.bold + colors.fg.red
        else:
            coloring = colors.reset
        print(coloring + message, colors.reset)

    def __call__(self, message: str = "", level: str = "INFO", *args, **kwargs):
        if level == "INFO" or level == "info":
            coloring = colors.bold + colors.fg.green
        elif level == "DEBUG" or level == "debug":
            coloring = colors.fg.lightblue
        elif level == "WARN" or level == "warning":
            coloring = colors.bold + colors.fg.yellow
        elif self.level == "ERROR":
            coloring = colors.fg.lightred
        elif self.level == "CRITICAL":
            coloring = colors.bold + colors.fg.red
        else:
            coloring = colors.reset
        print(coloring + message, colors.reset)
