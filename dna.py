import cyrus
import multiprocessing
import sys


def exception_handler(exception_type, exception, traceback):
    del traceback
    print("很抱歉，工具出现错误， 请把以下日志提交给开发者：")
    sys.stderr.write('{}: {}\n'.format(exception_type.__name__, exception))
    a = input("是否重启 [1=重启/0=退出]")
    if a == "1":
        init()


def init():
    cyrus.check_permissions()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    # sys.excepthook = exception_handler
    init()
