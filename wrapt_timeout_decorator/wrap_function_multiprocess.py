import sys
from .wrap_helper import raise_exception, is_system_windows
import multiprocess


class Timeout(object):
    """Wrap a function and add a timeout (limit) attribute to it.
    Instances of this class are automatically generated by the add_timeout
    function defined above. Wrapping a function allows asynchronous calls
    to be made and termination of execution after a timeout has passed.
    """

    def __init__(self, wrap_helper):
        """Initialize instance in preparation for being called."""
        self.wrap_helper = wrap_helper
        self.__name__ = self.wrap_helper.wrapped.__name__
        self.__doc__ = self.wrap_helper.wrapped.__doc__
        self.__process = None
        self.__parent_conn = None

    def __call__(self):
        """Execute the embedded function object asynchronously.
        The function given to the constructor is transparently called and
        requires that "ready" be intermittently polled. If and when it is
        True, the "value" property may then be checked for returned data.
        """
        self.__parent_conn, self.wrap_helper.child_conn = multiprocess.Pipe(duplex=False)
        self.__process = multiprocess.Process(target=_target, args=[self.wrap_helper])
        # daemonic process must not have subprocess - we need that for nested decorators
        self.__process.daemon = False
        self.__process.start()
        if not self.wrap_helper.dec_hard_timeout:
            self.wait_until_process_started()
        if self.__parent_conn.poll(self.wrap_helper.dec_timeout):
            return self.value
        else:
            self.cancel()

    def cancel(self):
        """Terminate any possible execution of the embedded function."""
        if self.__process.is_alive():
            self.__process.terminate()
        self.__process.join(timeout=1.0)
        self.__parent_conn.close()
        raise_exception(self.wrap_helper.timeout_exception, self.wrap_helper.exception_message)

    def wait_until_process_started(self):
        self.__parent_conn.recv()

    @property
    def value(self):
        exception_occured, result = self.__parent_conn.recv()
        # when self.__parent_conn.recv() exits, maybe __process is still alive,
        # then it might zombie the process. so join it explicitly
        self.__process.join(timeout=1.0)
        self.__parent_conn.close()

        if exception_occured:
            raise result
        else:
            return result


def _target(wrap_helper):
    """Run a function with arguments and return output via a pipe.
    This is a helper function for the Process created in Timeout. It runs
    the function with positional arguments and keyword arguments and then
    returns the function's output by way of a queue. If an exception gets
    raised, it is returned to Timeout to be raised by the value property.
    """
    # noinspection PyBroadException
    try:
        if not wrap_helper.dec_hard_timeout:
            wrap_helper.child_conn.send('started')
        exception_occured = False
        wrap_helper.child_conn.send((exception_occured, wrap_helper.wrapped(*wrap_helper.args, **wrap_helper.kwargs)))
    except Exception:
        exception_occured = True
        wrap_helper.child_conn.send((exception_occured, sys.exc_info()[1]))
    finally:
        wrap_helper.child_conn.close()


def is_python_27_under_windows():
    if is_system_windows() and sys.version_info < (3, 0):
        return True
    else:
        return False
