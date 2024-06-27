import os
import sys
import multiprocessing


def exception_handler(exception_type, exception, traceback):
    del traceback
    print("很抱歉，工具出现错误， 请把以下日志提交给开发者：")
    sys.stderr.write('{}: {}\n'.format(exception_type.__name__, exception))
    if input("是否重启 [1=重启/0=退出]") == "1":
        init()
    else:
        sys.exit(1)

def init():
    path = os.path.join(os.getcwd(),'py')
    sys.path.append(path)

    import cyrus
    cyrus.check_permissions()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    sys.excepthook = exception_handler
    init()