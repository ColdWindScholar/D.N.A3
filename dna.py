import cyrus
import multiprocessing
import sys


def exception_handler(exception_type, exception, traceback):
    del traceback
    print("很抱歉，工具出现错误， 请把以下日志提交给开发者：")
    sys.stderr.write('{}: {}\n'.format(exception_type.__name__, exception))
    input("任意按钮退出")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    sys.excepthook = exception_handler
    cyrus.check_permissions()
